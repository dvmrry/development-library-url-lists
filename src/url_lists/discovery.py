"""Free, conservative discovery of public package-repository endpoints."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .catalog import load_catalog, read_json, write_json_atomic
from .extractors import extract_registry_urls
from .normalize import TargetError, extract_urls, normalize_target, target_hostname


TRUSTED_NETWORK_HOSTS = {"api.github.com", "raw.githubusercontent.com"}
SOURCE_ROLES = frozenset(
    {"configuration", "documentation", "example", "official", "test"}
)
NON_CONFIGURATION_ROLES = frozenset({"documentation", "example", "test"})
HARD_REJECTION_FLAGS = frozenset({"documentation-like", "placeholder-like"})
PURL_TYPE_CATEGORIES = {
    "cargo": "rust",
    "cocoapods": "swift",
    "composer": "php",
    "conan": "cpp",
    "conda": "python",
    "cran": "r",
    "docker": "containers",
    "gem": "ruby",
    "golang": "go",
    "hackage": "haskell",
    "hex": "erlang",
    "julia": "julia",
    "maven": "jvm",
    "npm": "javascript",
    "nuget": "dotnet",
    "oci": "containers",
    "otp": "erlang",
    "pub": "dart",
    "pypi": "python",
    "swift": "swift",
    "vcpkg": "cpp",
}


class DiscoveryError(RuntimeError):
    """Raised when a trusted discovery source cannot be processed."""


class _TrustedRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        safe_url = _trusted_ascii_url(new_url)
        return super().redirect_request(request, fp, code, message, headers, safe_url)


_OPENER = build_opener(_TrustedRedirectHandler())


def _validate_network_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in TRUSTED_NETWORK_HOSTS:
        raise DiscoveryError(f"collector refused untrusted network endpoint: {url}")
    if parsed.username is not None or parsed.password is not None:
        raise DiscoveryError("collector refused credentials in a network endpoint")
    if parsed.port not in {None, 443}:
        raise DiscoveryError("collector refused a nonstandard network endpoint port")


def _trusted_ascii_url(url: str) -> str:
    """Validate a collector URL and safely encode attacker-controlled paths."""

    _validate_network_url(url)
    parsed = urlsplit(url)
    authority = parsed.hostname
    if parsed.port == 443:
        authority = f"{authority}:443"
    return urlunsplit(
        (
            "https",
            authority,
            quote(parsed.path, safe="/%:@-._~"),
            quote(parsed.query, safe="=&%"),
            "",
        )
    )


def _get_bytes(url: str, *, token: str | None = None) -> bytes:
    safe_url = _trusted_ascii_url(url)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "development-library-url-lists/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token and urlsplit(safe_url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
    request = Request(safe_url, headers=headers)
    try:
        with _OPENER.open(request, timeout=30) as response:
            return response.read(2_000_001)
    except (HTTPError, URLError, TimeoutError, UnicodeError) as error:
        raise DiscoveryError(
            f"trusted source request failed for {safe_url}: {error}"
        ) from error


def _get_json(url: str, *, token: str | None = None) -> Any:
    content = _get_bytes(url, token=token)
    if len(content) > 2_000_000:
        raise DiscoveryError(f"trusted source response is too large: {url}")
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DiscoveryError(f"trusted source returned invalid JSON: {url}") from error


def _get_text(url: str, *, token: str | None = None) -> str:
    content = _get_bytes(url, token=token)
    if len(content) > 2_000_000:
        raise DiscoveryError(f"trusted source response is too large: {url}")
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise DiscoveryError(f"trusted source returned non-UTF-8 text: {url}") from error


def _source_role(path: str) -> str:
    """Classify evidence without treating documentation as production config."""

    normalized = path.replace("\\", "/").lower().strip("/")
    parts = tuple(part for part in normalized.split("/") if part)
    directories = set(parts[:-1])
    filename = parts[-1] if parts else ""
    if (
        filename.startswith(("readme", "contributing"))
        or filename.endswith((".md", ".mdx", ".rst", ".adoc", ".asciidoc"))
        or directories.intersection({"doc", "docs", "documentation"})
    ):
        return "documentation"
    if directories.intersection(
        {"fixture", "fixtures", "spec", "specs", "test", "tests", "testing"}
    ):
        return "test"
    if directories.intersection(
        {"demo", "demos", "example", "examples", "sample", "samples"}
    ):
        return "example"
    return "configuration"


def _safe_log_text(value: str, *, maximum: int = 160) -> str:
    """Sanitize untrusted text for log output.

    Strips control characters (defeating log/workflow-command injection via
    hostile repository or path names) and truncates to a bounded length.
    """

    cleaned = "".join(
        character if character.isprintable() else "?" for character in value
    )
    cleaned = cleaned.replace("%", "%25")
    return cleaned[:maximum]


def collect_github_code(
    queries: Iterable[dict[str, Any]],
    *,
    token: str,
    delay_seconds: float = 7.0,
) -> list[dict[str, str]]:
    """Collect URLs from public package-manager configuration on GitHub."""

    observations: list[dict[str, str]] = []
    extraction_failures = 0
    query_list = list(queries)
    for query_index, query in enumerate(query_list):
        query_id = query["id"]
        ecosystem = query["ecosystem"]
        search_text = query["query"]
        extractor = query["extractor"]
        keys = query.get("keys", [])
        maximum = min(int(query.get("max_results", 10)), 100)
        search_url = (
            "https://api.github.com/search/code"
            f"?q={quote(search_text)}&per_page={maximum}"
        )
        result = _get_json(search_url, token=token)
        for item in result.get("items", []):
            content_url = item.get("url")
            evidence_url = item.get("html_url")
            source_path = item.get("path")
            repository = item.get("repository", {}).get("full_name")
            if not all(
                isinstance(value, str) and value
                for value in (content_url, evidence_url, source_path, repository)
            ):
                continue
            try:
                document = _get_json(content_url, token=token)
            except DiscoveryError:
                continue
            encoded = document.get("content")
            if document.get("encoding") != "base64" or not isinstance(encoded, str):
                continue
            try:
                decoded_bytes = base64.b64decode(
                    "".join(encoded.split()),
                    validate=True,
                )
                decoded = decoded_bytes.decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                continue
            content_sha256 = hashlib.sha256(decoded_bytes).hexdigest()
            try:
                discovered_urls = extract_registry_urls(
                    decoded,
                    extractor,
                    keys=keys,
                )
            except Exception as error:  # noqa: BLE001 - untrusted input boundary
                # A single degenerate or hostile public file must never abort
                # the whole discovery run; skip it, but report it so a
                # systemic parser regression cannot hide behind a green run.
                extraction_failures += 1
                print(
                    "Extraction failed and was skipped: "
                    f"query={_safe_log_text(query_id)} "
                    f"repository={_safe_log_text(repository)} "
                    f"path={_safe_log_text(source_path)} "
                    f"error={_safe_log_text(type(error).__name__)}",
                    file=sys.stderr,
                )
                continue
            for discovered_url in discovered_urls:
                observations.append(
                    {
                        "category": ecosystem,
                        "discovered_url": discovered_url,
                        "query_id": query_id,
                        "extractor": extractor,
                        "source": evidence_url,
                        "source_kind": "github-code",
                        "source_path": source_path,
                        "source_role": _source_role(source_path),
                        "repository": repository,
                        "content_sha256": content_sha256,
                    }
                )
        if query_index + 1 < len(query_list) and delay_seconds:
            time.sleep(delay_seconds)
    if extraction_failures:
        print(
            f"Discovery skipped {extraction_failures} file(s) whose "
            "extraction failed; see warnings above.",
            file=sys.stderr,
        )
    return observations


def collect_purl_definitions() -> list[dict[str, str]]:
    """Collect registry-like URLs from official Package-URL type definitions."""

    observations: list[dict[str, str]] = []
    index_url = (
        "https://raw.githubusercontent.com/package-url/purl-spec/"
        "main/purl-types-index.json"
    )
    available_types = _get_json(index_url)
    if not isinstance(available_types, list):
        raise DiscoveryError("Package-URL type index has an unexpected shape")

    for purl_type, category in PURL_TYPE_CATEGORIES.items():
        if purl_type not in available_types:
            continue
        source_url = (
            "https://raw.githubusercontent.com/package-url/purl-spec/main/"
            f"docs/types/definitions/{purl_type}-definition.md"
        )
        document = _get_text(source_url)
        content_sha256 = hashlib.sha256(document.encode("utf-8")).hexdigest()
        for line in document.splitlines():
            if not line.strip().lower().startswith("- **default repository url:**"):
                continue
            for discovered_url in extract_urls(line):
                observations.append(
                    {
                        "category": category,
                        "discovered_url": discovered_url,
                        "query_id": f"purl-{purl_type}-default",
                        "extractor": "purl-default-repository",
                        "source": source_url,
                        "source_kind": "purl-definition",
                        "source_path": (
                            f"docs/types/definitions/{purl_type}-definition.md"
                        ),
                        "source_role": "official",
                        "repository": "package-url/purl-spec",
                        "content_sha256": content_sha256,
                    }
                )
    return observations


def _is_excluded(hostname: str, exclusions: dict[str, Any]) -> bool:
    exact = {value.lower() for value in exclusions.get("exact_hosts", [])}
    suffixes = {value.lower() for value in exclusions.get("suffixes", [])}
    shared = {value.lower() for value in exclusions.get("shared_hosts", [])}
    if hostname in exact:
        return True
    if any(hostname.endswith(suffix) for suffix in suffixes):
        return True
    return any(hostname == value or hostname.endswith(f".{value}") for value in shared)


def _is_covered(target: str, catalog_entries: Iterable[dict[str, Any]]) -> bool:
    hostname = target_hostname(target)
    for entry in catalog_entries:
        if entry["status"] != "approved":
            continue
        known = entry["target"]
        if entry["match"] == "suffix":
            suffix = known.lstrip(".")
            if hostname == suffix or hostname.endswith(f".{suffix}"):
                return True
        elif entry["match"] == "path":
            if target == known or target.startswith(f"{known}/"):
                return True
        else:
            known_host = target_hostname(known)
            if hostname == known_host:
                return True
    return False


def filter_observations(
    observations: Iterable[dict[str, str]],
    *,
    exclusions: dict[str, Any],
    catalog_entries: Iterable[dict[str, Any]],
    rejected_targets: Iterable[str] = (),
) -> list[dict[str, str]]:
    """Normalize and conservatively filter untrusted observations."""

    rejected = set(rejected_targets)
    filtered: list[dict[str, str]] = []
    for observation in observations:
        try:
            target = normalize_target(
                observation["discovered_url"],
                preserve_path=False,
            )
            hostname = target_hostname(target)
        except (KeyError, TargetError):
            continue
        if target in rejected:
            continue
        if _is_excluded(hostname, exclusions):
            continue
        if _is_covered(target, catalog_entries):
            continue
        if HARD_REJECTION_FLAGS.intersection(_review_flags(target)):
            continue
        normalized = dict(observation)
        normalized["target"] = target
        del normalized["discovered_url"]
        filtered.append(normalized)
    return filtered


def _confidence(
    sources: list[dict[str, str]],
    review_flags: Iterable[str] = (),
) -> str:
    if "retired-service" in review_flags:
        return "low"
    if any(source.get("source_kind") == "purl-definition" for source in sources):
        return "high"
    repositories = {
        source["repository"]
        for source in sources
        if source.get("source_role", "configuration") == "configuration"
    }
    fingerprints = {
        source.get("content_sha256") or f"repository:{source['repository']}"
        for source in sources
        if source.get("source_role", "configuration") == "configuration"
    }
    independent_evidence = min(len(repositories), len(fingerprints))
    if independent_evidence >= 3:
        return "high"
    if independent_evidence >= 2:
        return "medium"
    return "low"


def _review_flags(
    target: str,
    sources: Iterable[dict[str, str]] = (),
) -> list[str]:
    hostname = target_hostname(target)
    flags: list[str] = []
    if (
        hostname.startswith(("doc.", "docs.", "documentation."))
        or hostname == "wikipedia.org"
        or hostname.endswith(".wikipedia.org")
        or hostname.endswith((".readthedocs.io", ".readthedocs.org"))
    ):
        flags.append("documentation-like")
    placeholder_labels = {
        "company",
        "example",
        "myhost",
        "mycompany",
        "placeholder",
        "youappname",
        "yourapp",
        "yourappname",
        "yourcompany",
        "yourdomain",
        "yourorg",
        "xxx",
        "yyy",
        "zzz",
    }
    if any(label in placeholder_labels for label in hostname.split(".")):
        flags.append("placeholder-like")
    if ":" in target.split("/", 1)[0]:
        flags.append("nonstandard-port")
    source_list = list(sources)
    if source_list and all(
        source.get("source_role", "configuration") in NON_CONFIGURATION_ROLES
        for source in source_list
    ):
        flags.append("non-configuration-evidence-only")
    if hostname == "bintray.com" or hostname.endswith(".bintray.com"):
        flags.append("retired-service")
    return flags


def merge_candidates(
    current: dict[str, Any],
    observations: Iterable[dict[str, str]],
    *,
    today: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Merge evidence without deleting candidates or manufacturing churn."""

    if current.get("schema_version") != 1 or not isinstance(
        current.get("candidates"), list
    ):
        raise DiscoveryError("unsupported candidates document")
    observed_date = today or datetime.now(timezone.utc).date().isoformat()
    by_target: dict[str, dict[str, Any]] = {
        candidate["target"]: dict(candidate) for candidate in current["candidates"]
    }
    additions = 0

    for candidate in by_target.values():
        sources = candidate.get("sources", [])
        review_flags = _review_flags(candidate["target"], sources)
        candidate["confidence"] = _confidence(sources, review_flags)
        candidate["review_flags"] = review_flags

    for observation in observations:
        target = observation["target"]
        source = {
            key: observation[key]
            for key in ("source", "source_kind", "repository")
        }
        for key in (
            "content_sha256",
            "extractor",
            "query_id",
            "source_path",
            "source_role",
        ):
            value = observation.get(key)
            if isinstance(value, str) and value:
                source[key] = value
        candidate = by_target.get(target)
        if candidate is None:
            candidate = {
                "target": target,
                "match": "exact",
                "categories": [],
                "confidence": "low",
                "first_seen": observed_date,
                "last_evidence_change": observed_date,
                "sources": [],
            }
            by_target[target] = candidate

        categories = set(candidate.get("categories", []))
        candidate_sources = candidate.setdefault("sources", [])
        source_identity = _source_identity(source)
        existing_source = next(
            (
                item
                for item in candidate_sources
                if _source_identity(item) == source_identity
            ),
            None,
        )
        changed = False
        if observation["category"] not in categories:
            categories.add(observation["category"])
            changed = True
        if existing_source is None:
            candidate_sources.append(source)
            changed = True
            additions += 1
        else:
            for key, value in source.items():
                if existing_source.get(key) != value:
                    existing_source[key] = value
                    changed = True
        candidate["categories"] = sorted(categories)
        candidate["sources"] = sorted(
            candidate_sources,
            key=lambda item: (
                item["source_kind"],
                item["repository"],
                item["source"],
            ),
        )
        review_flags = _review_flags(target, candidate["sources"])
        candidate["confidence"] = _confidence(candidate["sources"], review_flags)
        candidate["review_flags"] = review_flags
        if changed:
            candidate["last_evidence_change"] = observed_date

    candidates = sorted(
        by_target.values(),
        key=lambda item: item["target"].lstrip("."),
    )
    return {"schema_version": 1, "candidates": candidates}, additions


def _source_identity(source: dict[str, str]) -> tuple[str, str, str]:
    source_path = source.get("source_path")
    location = f"path:{source_path}" if source_path else f"url:{source['source']}"
    return source["source_kind"], source["repository"], location


def _discovery_rules_sha256(
    root: Path,
    queries: dict[str, Any],
    exclusions: dict[str, Any],
) -> str:
    """Fingerprint the configuration and code that decide candidate inclusion."""

    digest = hashlib.sha256()
    for label, value in (("queries", queries), ("exclusions", exclusions)):
        digest.update(label.encode("utf-8"))
        digest.update(
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        )
    for relative_path in (
        "src/url_lists/discovery.py",
        "src/url_lists/extractors.py",
        "src/url_lists/normalize.py",
    ):
        try:
            content = (root / relative_path).read_text(encoding="utf-8")
        except OSError as error:
            raise DiscoveryError(
                f"cannot fingerprint discovery rule file {relative_path}: {error}"
            ) from error
        digest.update(relative_path.encode("utf-8"))
        digest.update(content.replace("\r\n", "\n").encode("utf-8"))
    return digest.hexdigest()


def _reconcile_current_candidates(
    current: dict[str, Any],
    *,
    rules_sha256: str,
    exclusions: dict[str, Any],
    catalog_entries: Iterable[dict[str, Any]],
    rejected_targets: Iterable[str],
) -> dict[str, Any]:
    """Drop stale-rule snapshots and entries resolved by deterministic policy."""

    if current.get("schema_version") != 1 or not isinstance(
        current.get("candidates"), list
    ):
        raise DiscoveryError("unsupported candidates document")
    reconciled = {
        "schema_version": 1,
        "discovery_rules_sha256": rules_sha256,
        "candidates": [],
    }
    if current.get("discovery_rules_sha256") != rules_sha256:
        return reconciled

    rejected = set(rejected_targets)
    for candidate in current["candidates"]:
        try:
            target = normalize_target(candidate["target"], preserve_path=False)
            hostname = target_hostname(target)
        except (KeyError, TargetError, TypeError):
            continue
        if target in rejected:
            continue
        if _is_excluded(hostname, exclusions):
            continue
        if _is_covered(target, catalog_entries):
            continue
        if HARD_REJECTION_FLAGS.intersection(
            _review_flags(target, candidate.get("sources", []))
        ):
            continue
        reconciled["candidates"].append(candidate)
    return reconciled


def run_network_discovery(root: Path, *, token: str | None = None) -> int:
    """Run all collectors and persist newly evidenced candidates."""

    github_token = token or os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise DiscoveryError("GITHUB_TOKEN is required for GitHub code search")

    queries_document = read_json(root / "data" / "search_queries.json")
    queries = queries_document.get("queries", [])
    exclusions = read_json(root / "data" / "discovery_exclusions.json")
    rejections = read_json(root / "data" / "rejections.json")
    if rejections.get("schema_version") != 1 or not isinstance(
        rejections.get("rejections"), list
    ):
        raise DiscoveryError("unsupported rejections document")
    catalog = load_catalog(root)
    observations = collect_github_code(queries, token=github_token)
    observations.extend(collect_purl_definitions())
    observations = filter_observations(
        observations,
        exclusions=exclusions,
        catalog_entries=catalog["entries"],
        rejected_targets={
            rejection["target"] for rejection in rejections["rejections"]
        },
    )

    candidates_path = root / "data" / "candidates.json"
    current = read_json(candidates_path)
    rules_sha256 = _discovery_rules_sha256(root, queries_document, exclusions)
    current = _reconcile_current_candidates(
        current,
        rules_sha256=rules_sha256,
        exclusions=exclusions,
        catalog_entries=catalog["entries"],
        rejected_targets={
            rejection["target"] for rejection in rejections["rejections"]
        },
    )
    merged, additions = merge_candidates(current, observations)
    merged["discovery_rules_sha256"] = rules_sha256
    if merged != current:
        write_json_atomic(candidates_path, merged)
    return additions

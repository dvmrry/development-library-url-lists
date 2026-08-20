"""Free, conservative discovery of public package-repository endpoints."""

from __future__ import annotations

import base64
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .catalog import load_catalog, read_json, write_json_atomic
from .normalize import TargetError, extract_urls, normalize_target, target_hostname


TRUSTED_NETWORK_HOSTS = {"api.github.com", "raw.githubusercontent.com"}
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
        _validate_network_url(new_url)
        return super().redirect_request(request, fp, code, message, headers, new_url)


_OPENER = build_opener(_TrustedRedirectHandler())


def _validate_network_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in TRUSTED_NETWORK_HOSTS:
        raise DiscoveryError(f"collector refused untrusted network endpoint: {url}")


def _get_bytes(url: str, *, token: str | None = None) -> bytes:
    _validate_network_url(url)
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "development-library-url-lists/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token and urlsplit(url).hostname == "api.github.com":
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    try:
        with _OPENER.open(request, timeout=30) as response:
            return response.read(2_000_001)
    except (HTTPError, URLError, TimeoutError) as error:
        raise DiscoveryError(f"trusted source request failed for {url}: {error}") from error


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


def collect_github_code(
    queries: Iterable[dict[str, Any]],
    *,
    token: str,
    delay_seconds: float = 7.0,
) -> list[dict[str, str]]:
    """Collect URLs from public package-manager configuration on GitHub."""

    observations: list[dict[str, str]] = []
    query_list = list(queries)
    for query_index, query in enumerate(query_list):
        ecosystem = query["ecosystem"]
        search_text = query["query"]
        maximum = min(int(query.get("max_results", 10)), 100)
        search_url = (
            "https://api.github.com/search/code"
            f"?q={quote(search_text)}&per_page={maximum}"
        )
        result = _get_json(search_url, token=token)
        for item in result.get("items", []):
            content_url = item.get("url")
            evidence_url = item.get("html_url")
            repository = item.get("repository", {}).get("full_name")
            if not all(
                isinstance(value, str) and value
                for value in (content_url, evidence_url, repository)
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
                decoded = base64.b64decode(
                    "".join(encoded.split()),
                    validate=True,
                ).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                continue
            context_terms = query.get("context_terms", [])
            for discovered_url in extract_context_urls(decoded, context_terms):
                observations.append(
                    {
                        "category": ecosystem,
                        "discovered_url": discovered_url,
                        "source": evidence_url,
                        "source_kind": "github-code",
                        "repository": repository,
                    }
                )
        if query_index + 1 < len(query_list) and delay_seconds:
            time.sleep(delay_seconds)
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
        for line in document.splitlines():
            if not line.strip().lower().startswith("- **default repository url:**"):
                continue
            for discovered_url in extract_urls(line):
                observations.append(
                    {
                        "category": category,
                        "discovered_url": discovered_url,
                        "source": source_url,
                        "source_kind": "purl-definition",
                        "repository": "package-url/purl-spec",
                    }
                )
    return observations


def extract_context_urls(text: str, context_terms: Iterable[str]) -> list[str]:
    """Extract URLs only from lines relevant to the searched setting."""

    terms = [term.lower() for term in context_terms if term]
    if not terms:
        return extract_urls(text)

    lines = text.splitlines()
    selected: set[int] = set()
    for index, line in enumerate(lines):
        if any(term in line.lower() for term in terms):
            selected.add(index)

    urls: list[str] = []
    seen: set[str] = set()
    for index in sorted(selected):
        for url in extract_urls(lines[index]):
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


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
) -> list[dict[str, str]]:
    """Normalize and conservatively filter untrusted observations."""

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
        if _is_excluded(hostname, exclusions):
            continue
        if _is_covered(target, catalog_entries):
            continue
        normalized = dict(observation)
        normalized["target"] = target
        del normalized["discovered_url"]
        filtered.append(normalized)
    return filtered


def _confidence(sources: list[dict[str, str]]) -> str:
    repositories = {source["repository"] for source in sources}
    kinds = {source["source_kind"] for source in sources}
    if len(repositories) >= 3 or len(kinds) >= 2:
        return "high"
    if len(repositories) >= 2:
        return "medium"
    return "low"


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

    for observation in observations:
        target = observation["target"]
        source = {
            key: observation[key]
            for key in ("source", "source_kind", "repository")
        }
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
        source_identities = {
            (item["source"], item["source_kind"], item["repository"])
            for item in candidate.get("sources", [])
        }
        changed = False
        if observation["category"] not in categories:
            categories.add(observation["category"])
            changed = True
        source_identity = (
            source["source"],
            source["source_kind"],
            source["repository"],
        )
        if source_identity not in source_identities:
            candidate.setdefault("sources", []).append(source)
            changed = True
            additions += 1
        candidate["categories"] = sorted(categories)
        candidate["sources"] = sorted(
            candidate["sources"],
            key=lambda item: (
                item["source_kind"],
                item["repository"],
                item["source"],
            ),
        )
        candidate["confidence"] = _confidence(candidate["sources"])
        if changed:
            candidate["last_evidence_change"] = observed_date

    candidates = sorted(
        by_target.values(),
        key=lambda item: item["target"].lstrip("."),
    )
    return {"schema_version": 1, "candidates": candidates}, additions


def run_network_discovery(root: Path, *, token: str | None = None) -> int:
    """Run all collectors and persist newly evidenced candidates."""

    github_token = token or os.environ.get("GITHUB_TOKEN")
    if not github_token:
        raise DiscoveryError("GITHUB_TOKEN is required for GitHub code search")

    queries = read_json(root / "data" / "search_queries.json").get("queries", [])
    exclusions = read_json(root / "data" / "discovery_exclusions.json")
    catalog = load_catalog(root)
    observations = collect_github_code(queries, token=github_token)
    observations.extend(collect_purl_definitions())
    observations = filter_observations(
        observations,
        exclusions=exclusions,
        catalog_entries=catalog["entries"],
    )

    candidates_path = root / "data" / "candidates.json"
    current = read_json(candidates_path)
    merged, additions = merge_candidates(current, observations)
    if merged != current:
        write_json_atomic(candidates_path, merged)
    return additions

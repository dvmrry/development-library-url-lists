"""Deterministic collectors for public registry and mirror catalogs."""

from __future__ import annotations

import csv
from dataclasses import dataclass
import hashlib
import io
import json
import os
import sys
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .normalize import TargetError, normalize_target


MAX_SOURCE_BYTES = 2_000_000
PUBLISHED_SOURCE_HOSTS = frozenset(
    {
        "archlinux.org",
        "cran.r-project.org",
        "mirror-master.debian.org",
        "mirrors.alpinelinux.org",
        "mirrors.cernet.edu.cn",
        "packages.ecosyste.ms",
    }
)
ECOSYSTEM_CATEGORIES = {
    "actions": "multi_ecosystem",
    "adelie": "os_packages",
    "alpine": "os_packages",
    "bazel": "multi_ecosystem",
    "bioconductor": "r",
    "bower": "javascript",
    "brew": "os_packages",
    "cargo": "rust",
    "carthage": "swift",
    "clojars": "jvm",
    "cocoapods": "swift",
    "composer": "php",
    "conan": "cpp",
    "conda": "python",
    "cpan": "multi_ecosystem",
    "cran": "r",
    "ctan": "multi_ecosystem",
    "debian": "os_packages",
    "deno": "javascript",
    "docker": "containers",
    "elm": "multi_ecosystem",
    "fdroid": "os_packages",
    "freebsd": "os_packages",
    "gem": "ruby",
    "gentoo": "os_packages",
    "githubactions": "multi_ecosystem",
    "golang": "go",
    "guix": "os_packages",
    "hackage": "haskell",
    "helm": "containers",
    "hex": "erlang",
    "ips": "os_packages",
    "julia": "julia",
    "lean": "multi_ecosystem",
    "maven": "jvm",
    "melpa": "multi_ecosystem",
    "nix": "os_packages",
    "npm": "javascript",
    "nuget": "dotnet",
    "openbsd": "os_packages",
    "openvsx": "multi_ecosystem",
    "packagist": "php",
    "pkgsrc": "os_packages",
    "postmarketos": "os_packages",
    "pub": "dart",
    "puppet": "multi_ecosystem",
    "pypi": "python",
    "racket": "multi_ecosystem",
    "rubygems": "ruby",
    "spack": "multi_ecosystem",
    "swift": "swift",
    "terraform": "multi_ecosystem",
    "ubuntu": "os_packages",
    "vcpkg": "cpp",
}

ECOSYSTEMS_URL = (
    "https://packages.ecosyste.ms/api/v1/registries?page={page}&per_page=100"
)
MIRRORZ_URL = "https://mirrors.cernet.edu.cn/api/scoring"
CRAN_URL = "https://cran.r-project.org/CRAN_mirrors.csv"
ALPINE_URL = "https://mirrors.alpinelinux.org/mirrors.txt"
ARCH_URL = "https://archlinux.org/mirrors/status/json/"
DEBIAN_URL = "https://mirror-master.debian.org/status/Mirrors.masterlist"


class PublishedSourceError(RuntimeError):
    """Raised when a published source cannot be fetched or parsed safely."""


@dataclass(frozen=True)
class PublishedCollection:
    observations: list[dict[str, str]]
    successful_query_ids: frozenset[str]
    failed_query_ids: frozenset[str]


def _validate_source_url(url: str) -> None:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname not in PUBLISHED_SOURCE_HOSTS:
        raise PublishedSourceError(f"refused untrusted published source: {url}")
    if parsed.username is not None or parsed.password is not None:
        raise PublishedSourceError("refused credentials in a published source URL")
    if parsed.port not in {None, 443}:
        raise PublishedSourceError("refused a nonstandard published source port")


def _safe_source_url(url: str) -> str:
    _validate_source_url(url)
    parsed = urlsplit(url)
    authority = parsed.hostname or ""
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


class _PublishedRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return super().redirect_request(
            request,
            fp,
            code,
            message,
            headers,
            _safe_source_url(new_url),
        )


_OPENER = build_opener(_PublishedRedirectHandler())


def _fetch_bytes(url: str) -> bytes:
    safe_url = _safe_source_url(url)
    request = Request(
        safe_url,
        headers={
            "Accept": "application/json,text/csv,text/plain;q=0.9,*/*;q=0.1",
            "User-Agent": "development-library-url-lists/0.1",
        },
    )
    try:
        with _OPENER.open(request, timeout=30) as response:
            content = response.read(MAX_SOURCE_BYTES + 1)
    except (HTTPError, URLError, TimeoutError, UnicodeError) as error:
        raise PublishedSourceError(
            f"published source request failed for {safe_url}: {type(error).__name__}"
        ) from error
    if len(content) > MAX_SOURCE_BYTES:
        raise PublishedSourceError(f"published source is too large: {safe_url}")
    return content


def _decode_text(content: bytes, source_url: str) -> str:
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise PublishedSourceError(
            f"published source returned non-UTF-8 text: {source_url}"
        ) from error


def _decode_json(content: bytes, source_url: str) -> Any:
    try:
        return json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PublishedSourceError(
            f"published source returned invalid JSON: {source_url}"
        ) from error


def _record_sha256(*values: str) -> str:
    """Fingerprint stable admission evidence, not volatile whole-feed metadata."""

    return hashlib.sha256("\0".join(values).encode("utf-8")).hexdigest()


def _observation(
    discovered_url: str,
    *,
    category: str,
    source: str,
    source_role: str,
    repository: str,
    extractor: str,
    query_id: str,
    source_path: str,
    source_ecosystem: str | None = None,
) -> dict[str, str]:
    observation = {
        "category": category,
        "discovered_url": discovered_url,
        "source": source,
        "source_kind": "published-list",
        "source_role": source_role,
        "repository": repository,
        "content_sha256": _record_sha256(
            query_id,
            discovered_url,
            category,
            source_ecosystem or "",
        ),
        "extractor": extractor,
        "query_id": query_id,
        "source_path": source_path,
    }
    if source_ecosystem:
        observation["source_ecosystem"] = source_ecosystem
    return observation


def _deduplicate(observations: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Keep one deterministic observation per target and published source."""

    selected: dict[tuple[str, str], dict[str, str]] = {}
    for observation in observations:
        try:
            target = normalize_target(
                observation["discovered_url"],
                preserve_path=False,
            )
        except (KeyError, TargetError):
            continue
        identity = (target, observation["query_id"])
        current = selected.get(identity)
        if current is None or observation["discovered_url"].startswith("https://"):
            selected[identity] = observation
    return sorted(
        selected.values(),
        key=lambda item: (
            normalize_target(item["discovered_url"], preserve_path=False),
            item["query_id"],
        ),
    )


def parse_ecosystems_registries(
    payload: Any,
    *,
    source_url: str,
) -> list[dict[str, str]]:
    if not isinstance(payload, list):
        raise PublishedSourceError("ecosyste.ms registry catalog has an unexpected shape")

    observations: list[dict[str, str]] = []
    for record in payload:
        if not isinstance(record, dict):
            continue
        source_ecosystem = record.get("purl_type") or record.get("ecosystem")
        if not isinstance(source_ecosystem, str):
            continue
        category = ECOSYSTEM_CATEGORIES.get(source_ecosystem.lower())
        if category is None:
            continue
        urls = [record.get("url")]
        metadata = record.get("metadata")
        if isinstance(metadata, dict):
            urls.append(metadata.get("api_url"))
        for discovered_url in urls:
            if not isinstance(discovered_url, str) or not discovered_url.startswith(
                ("https://", "http://")
            ):
                continue
            observations.append(
                _observation(
                    discovered_url,
                    category=category,
                    source=source_url,
                    source_role="registry-catalog",
                    repository="ecosyste-ms/packages",
                    extractor="ecosystems-registry-json",
                    query_id="ecosystems-registries",
                    source_path=discovered_url,
                    source_ecosystem=source_ecosystem.lower(),
                )
            )
    return _deduplicate(observations)


def parse_mirrorz_scoring(
    payload: Any,
) -> list[dict[str, str]]:
    rows = payload.get("scores") if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise PublishedSourceError("MirrorZ scoring catalog has an unexpected shape")
    observations = []
    for record in rows:
        hostname = record.get("resolve") if isinstance(record, dict) else None
        if not isinstance(hostname, str) or not hostname.strip():
            continue
        discovered_url = f"https://{hostname.strip().lower()}"
        observations.append(
            _observation(
                discovered_url,
                category="multi_ecosystem",
                source=MIRRORZ_URL,
                source_role="mirror-catalog",
                repository="mirrorz-org/mirrorz-302",
                extractor="mirrorz-scoring-json",
                query_id="mirrorz-public-mirrors",
                source_path=discovered_url,
            )
        )
    return _deduplicate(observations)


def parse_cran_mirrors(text: str) -> list[dict[str, str]]:
    observations = []
    for row in csv.DictReader(io.StringIO(text)):
        discovered_url = row.get("URL")
        if row.get("OK") != "1" or not isinstance(discovered_url, str):
            continue
        observations.append(
            _observation(
                discovered_url,
                category="r",
                source=CRAN_URL,
                source_role="official",
                repository="r-project/cran-mirrors",
                extractor="cran-mirrors-csv",
                query_id="cran-official-mirrors",
                source_path=discovered_url,
                source_ecosystem="cran",
            )
        )
    return _deduplicate(observations)


def parse_alpine_mirrors(text: str) -> list[dict[str, str]]:
    observations = []
    for line in text.splitlines():
        discovered_url = line.strip()
        if not discovered_url or discovered_url.startswith("#"):
            continue
        observations.append(
            _observation(
                discovered_url,
                category="os_packages",
                source=ALPINE_URL,
                source_role="official",
                repository="alpinelinux/mirrors",
                extractor="alpine-mirrors-text",
                query_id="alpine-official-mirrors",
                source_path=discovered_url,
                source_ecosystem="alpine",
            )
        )
    return _deduplicate(observations)


def parse_arch_mirrors(payload: Any) -> list[dict[str, str]]:
    rows = payload.get("urls") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise PublishedSourceError("Arch mirror status has an unexpected shape")
    observations = []
    for row in rows:
        if not isinstance(row, dict) or row.get("active") is not True:
            continue
        completion = row.get("completion_pct")
        score = row.get("score")
        discovered_url = row.get("url")
        if (
            not isinstance(completion, (int, float))
            or isinstance(completion, bool)
            or completion < 0.9
            or not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not isinstance(discovered_url, str)
            or not discovered_url.startswith(("https://", "http://"))
        ):
            continue
        observations.append(
            _observation(
                discovered_url,
                category="os_packages",
                source=ARCH_URL,
                source_role="official",
                repository="archlinux/mirror-status",
                extractor="arch-mirror-status-json",
                query_id="arch-official-active-mirrors",
                source_path=discovered_url,
                source_ecosystem="archlinux",
            )
        )
    return _deduplicate(observations)


def parse_debian_masterlist(
    text: str,
) -> list[dict[str, str]]:
    observations = []
    for paragraph in text.replace("\r\n", "\n").split("\n\n"):
        fields: dict[str, str] = {}
        for line in paragraph.splitlines():
            key, separator, value = line.partition(":")
            if separator:
                fields[key.strip()] = value.strip()
        site = fields.get("Site")
        if not site:
            continue
        endpoint_fields = sorted(
            (key, value)
            for key, value in fields.items()
            if key.lower().endswith(("-http", "-https")) and value
        )
        for key, path in endpoint_fields:
            scheme = "https" if key.lower().endswith("-https") else "http"
            normalized_path = path if path.startswith("/") else f"/{path}"
            discovered_url = f"{scheme}://{site}{normalized_path}"
            observations.append(
                _observation(
                    discovered_url,
                    category="os_packages",
                    source=DEBIAN_URL,
                    source_role="official",
                    repository="debian/mirror-masterlist",
                    extractor="debian-masterlist",
                    query_id="debian-official-mirrors",
                    source_path=discovered_url,
                    source_ecosystem="debian",
                )
            )
    return _deduplicate(observations)


def _collect_json_source(
    url: str,
    parser: Callable[..., list[dict[str, str]]],
    *,
    fetch: Callable[[str], bytes],
) -> list[dict[str, str]]:
    content = fetch(url)
    return parser(_decode_json(content, url))


def _collect_text_source(
    url: str,
    parser: Callable[..., list[dict[str, str]]],
    *,
    fetch: Callable[[str], bytes],
) -> list[dict[str, str]]:
    content = fetch(url)
    return parser(_decode_text(content, url))


def _collect_ecosystems(
    *,
    fetch: Callable[[str], bytes],
) -> list[dict[str, str]]:
    observations: list[dict[str, str]] = []
    for page in range(1, 11):
        source_url = ECOSYSTEMS_URL.format(page=page)
        content = fetch(source_url)
        payload = _decode_json(content, source_url)
        page_observations = parse_ecosystems_registries(
            payload,
            source_url=source_url,
        )
        observations.extend(page_observations)
        if not isinstance(payload, list) or len(payload) < 100:
            break
    else:
        raise PublishedSourceError("ecosyste.ms pagination exceeded the safety limit")
    return _deduplicate(observations)


def collect_published_sources(
    *,
    fetch: Callable[[str], bytes] = _fetch_bytes,
) -> PublishedCollection:
    """Fetch every configured catalog, preserving partial success explicitly."""

    collectors: tuple[
        tuple[str, str, int, Callable[[], list[dict[str, str]]]], ...
    ] = (
        (
            "ecosyste.ms",
            "ecosystems-registries",
            20,
            lambda: _collect_ecosystems(fetch=fetch),
        ),
        (
            "MirrorZ",
            "mirrorz-public-mirrors",
            5,
            lambda: _collect_json_source(
                MIRRORZ_URL,
                parse_mirrorz_scoring,
                fetch=fetch,
            ),
        ),
        (
            "CRAN",
            "cran-official-mirrors",
            20,
            lambda: _collect_text_source(CRAN_URL, parse_cran_mirrors, fetch=fetch),
        ),
        (
            "Alpine",
            "alpine-official-mirrors",
            20,
            lambda: _collect_text_source(
                ALPINE_URL,
                parse_alpine_mirrors,
                fetch=fetch,
            ),
        ),
        (
            "Arch",
            "arch-official-active-mirrors",
            50,
            lambda: _collect_json_source(ARCH_URL, parse_arch_mirrors, fetch=fetch),
        ),
        (
            "Debian",
            "debian-official-mirrors",
            50,
            lambda: _collect_text_source(
                DEBIAN_URL,
                parse_debian_masterlist,
                fetch=fetch,
            ),
        ),
    )
    observations: list[dict[str, str]] = []
    failures: list[str] = []
    successful_query_ids: set[str] = set()
    failed_query_ids: set[str] = set()
    for name, query_id, minimum, collector in collectors:
        try:
            collected = collector()
            if len(collected) < minimum:
                raise PublishedSourceError(
                    f"{name} returned {len(collected)} records; expected at least {minimum}"
                )
            observations.extend(collected)
            successful_query_ids.add(query_id)
            print(f"Published source {name}: {len(collected)} observation(s)")
        except PublishedSourceError as error:
            failures.append(name)
            failed_query_ids.add(query_id)
            safe_error = "".join(
                character if character.isprintable() else "?"
                for character in str(error)
            )[:300]
            message = f"Published source {name} was skipped: {safe_error}"
            if os.environ.get("GITHUB_ACTIONS") == "true":
                encoded = safe_error.replace("%", "%25")
                print(f"::warning title=Published source {name}::{encoded}")
            else:
                print(message, file=sys.stderr)
    if len(failures) == len(collectors):
        raise PublishedSourceError("all published source collectors failed")
    if failures:
        print(
            "Published discovery completed with failed source(s): "
            + ", ".join(failures),
            file=sys.stderr,
        )
    return PublishedCollection(
        observations=_deduplicate(observations),
        successful_query_ids=frozenset(successful_query_ids),
        failed_query_ids=frozenset(failed_query_ids),
    )

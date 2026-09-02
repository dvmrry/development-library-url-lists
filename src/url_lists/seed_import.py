"""Import package-manager observations from an offline BigQuery GitHub seed."""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Iterable, TextIO
from urllib.parse import quote

from .catalog import load_catalog, load_categories, read_json, write_json_atomic
from .discovery import (
    _safe_log_text,
    _source_role,
    filter_observations,
    merge_candidates,
)
from .extractors import SUPPORTED_EXTRACTORS, extract_registry_urls
from .review_queue import write_review_queue


SOURCE_KIND = "bigquery-github"
# A public registry appears across many independent public repositories; one
# organisation's private endpoint appears only in that organisation's few
# open-sourced repositories. At GitHub-search scale this count mostly measured
# the 20-result search cap, but a bulk seed can see real reach, which makes it
# the primary defence against flooding review with other people's internal
# infrastructure.
DEFAULT_MINIMUM_REPOSITORIES = 5
QUERY_ID = "bigquery-github"
MAX_CONTENT_BYTES = 2_000_000
# A JSON string may use up to six ASCII characters for one escaped Unicode
# code point. Keep a generous bound for the raw line while still rejecting an
# accidentally unbounded line before handing it to json.loads().
MAX_RECORD_BYTES = MAX_CONTENT_BYTES * 8 + 4_096

OBSERVATION_KEYS = (
    "category",
    "discovered_url",
    "query_id",
    "extractor",
    "source",
    "source_kind",
    "source_path",
    "source_role",
    "repository",
    "content_sha256",
)

# These are deliberately keyed by the extractor rather than by a guessed URL
# or by arbitrary text in the file. The values are the existing ids from
# data/categories.json.
EXTRACTOR_CATEGORIES = {
    "bunfig-toml": "javascript",
    "cargo-toml": "rust",
    "composer-json": "php",
    "conan-cli": "cpp",
    "conan-json": "cpp",
    "conda-yaml": "python",
    "docker-json": "containers",
    "gradle-repository": "jvm",
    "maven-pom-xml": "jvm",
    "maven-settings-xml": "jvm",
    "msbuild-restore-sources": "dotnet",
    "npmrc": "javascript",
    "nuget-xml": "dotnet",
    "package-json-registry": "javascript",
    "paket-dependencies": "dotnet",
    "pip-config": "python",
    "pip-requirements": "python",
    "python-toml-sources": "python",
    "r-repositories": "r",
    "ruby-source": "ruby",
    "sbt-resolver": "jvm",
    "stack-yaml": "haskell",
    "swift-registries-json": "swift",
    "uv-toml": "python",
    "yarnrc-v1": "javascript",
    "yarnrc-yaml": "javascript",
}

# Explicit basename mappings keep an unsupported file from being interpreted
# with whichever parser happens to find a URL in it. Some extractors have no
# unambiguous filename in the fixed seed contract (for example the
# key-dependent environment-assignment extractor), so they are intentionally
# not mapped here.
_BASENAME_EXTRACTORS = {
    "bunfig.toml": "bunfig-toml",
    "cargo.toml": "cargo-toml",
    "composer.json": "composer-json",
    "daemon.json": "docker-json",
    ".condarc": "conda-yaml",
    "config.toml": "cargo-toml",
    "environment.yml": "conda-yaml",
    "environment.yaml": "conda-yaml",
    "gemfile": "ruby-source",
    "nuget.config": "nuget-xml",
    ".npmrc": "npmrc",
    "package.json": "package-json-registry",
    "paket.dependencies": "paket-dependencies",
    "pip.conf": "pip-config",
    "pip.ini": "pip-config",
    "pipfile": "python-toml-sources",
    "podfile": "ruby-source",
    "pom.xml": "maven-pom-xml",
    "pyproject.toml": "python-toml-sources",
    "registries.json": "swift-registries-json",
    "remotes.json": "conan-json",
    "settings.xml": "maven-settings-xml",
    "stack.yaml": "stack-yaml",
    "stack.yml": "stack-yaml",
    ".yarnrc": "yarnrc-v1",
    ".yarnrc.yml": "yarnrc-yaml",
}


class SeedImportError(RuntimeError):
    """Raised when the seed file or trusted repository data cannot be read."""


@dataclass(frozen=True)
class SeedImportResult:
    """Counts and observations produced by one seed import pass."""

    observations: list[dict[str, str]]
    records_read: int
    skipped: int
    candidates_added: int = 0

    @property
    def observations_produced(self) -> int:
        return len(self.observations)


def _warning_stream(stderr: TextIO | None) -> TextIO:
    return stderr if stderr is not None else sys.stderr


def _record_label(record: Any) -> str:
    if not isinstance(record, dict):
        return ""
    details: list[str] = []
    for key in ("repo_name", "path"):
        value = record.get(key)
        if isinstance(value, str) and value:
            details.append(f"{key}={_safe_log_text(value)}")
    return f" ({' '.join(details)})" if details else ""


def _warn(
    stream: TextIO,
    record_number: int,
    reason: str,
    record: Any = None,
) -> None:
    print(
        f"Seed record {record_number} skipped: {reason}{_record_label(record)}",
        file=stream,
    )


def _basename(path: str) -> str:
    # GitHub paths use forward slashes. Treat backslashes as separators for
    # classification as well, while leaving the original path untouched in
    # provenance and in the evidence URL.
    return path.replace("\\", "/").rsplit("/", 1)[-1].casefold()


def map_path_to_extractor(path: str) -> str | None:
    """Return the known extractor for a seed path, or ``None`` if unknown."""

    if not isinstance(path, str):
        return None
    filename = _basename(path)
    extractor = _BASENAME_EXTRACTORS.get(filename)
    if extractor is not None:
        return extractor if extractor in SUPPORTED_EXTRACTORS else None
    if filename.startswith("requirements") and filename.endswith(".txt"):
        return "pip-requirements"
    if filename.endswith((".gradle", ".gradle.kts")):
        return "gradle-repository"
    if filename.endswith(".sbt"):
        return "sbt-resolver"
    if filename.endswith((".props", ".csproj")):
        return "msbuild-restore-sources"
    if filename.endswith(".r"):
        return "r-repositories"
    return None


# A short alias makes the mapping helper easy to discover for callers without
# creating a second source of truth.
extractor_for_path = map_path_to_extractor


def _category_for_path(path: str, extractor: str) -> str | None:
    category = EXTRACTOR_CATEGORIES.get(extractor)
    if category is None:
        return None
    # The existing ruby-source extractor serves both Gemfile (Ruby) and
    # Podfile (Swift) search queries. Preserve that path-specific distinction
    # when the same extractor is used by the offline seed.
    if extractor == "ruby-source" and _basename(path) == "podfile":
        return "swift"
    return category


def _quote_github_path(value: str) -> str:
    """Quote a path while retaining separators and neutralizing dot segments."""

    quoted_segments: list[str] = []
    for segment in value.split("/"):
        if segment == ".":
            quoted_segments.append("%2E")
        elif segment == "..":
            quoted_segments.append("%2E%2E")
        else:
            # Do not preserve '%' from attacker input: an input such as
            # '%2e%2e' must not become a second decoding of '..'.
            quoted_segments.append(quote(segment, safe="-._~"))
    return "/".join(quoted_segments)


def _source_url(repository: str, path: str) -> str:
    return (
        "https://github.com/"
        f"{_quote_github_path(repository)}/blob/HEAD/"
        f"{_quote_github_path(path)}"
    )


def _decode_json_line(
    line: bytes | str,
    *,
    record_number: int,
    stderr: TextIO,
) -> tuple[Any | None, bool]:
    """Decode one raw JSONL line, returning (value, was_skipped)."""

    if isinstance(line, bytes):
        if len(line) > MAX_RECORD_BYTES:
            _warn(stderr, record_number, "record is too large")
            return None, True
        try:
            line = line.decode("utf-8")
        except UnicodeDecodeError:
            _warn(stderr, record_number, "record is not valid UTF-8")
            return None, True
    elif isinstance(line, str):
        try:
            if len(line.encode("utf-8")) > MAX_RECORD_BYTES:
                _warn(stderr, record_number, "record is too large")
                return None, True
        except UnicodeEncodeError:
            _warn(stderr, record_number, "record is not valid UTF-8")
            return None, True
    else:
        _warn(stderr, record_number, "record is not JSON text")
        return None, True

    try:
        value = json.loads(line)
    except Exception as error:  # noqa: BLE001 - untrusted JSON boundary
        _warn(stderr, record_number, f"invalid JSON ({type(error).__name__})")
        return None, True
    return value, False


def _record_observations(
    record: Any,
    *,
    record_number: int,
    stderr: TextIO,
) -> tuple[list[dict[str, str]], bool]:
    if not isinstance(record, dict):
        _warn(stderr, record_number, "record must be a JSON object", record)
        return [], True

    repo_name = record.get("repo_name")
    path = record.get("path")
    content = record.get("content")
    if not (
        isinstance(repo_name, str)
        and repo_name
        and repo_name.strip()
        and isinstance(path, str)
        and path
        and isinstance(content, str)
    ):
        _warn(
            stderr,
            record_number,
            "repo_name, path, and content must have valid string types",
            record,
        )
        return [], True

    extractor = map_path_to_extractor(path)
    if extractor is None:
        _warn(stderr, record_number, "path has no known extractor", record)
        return [], True
    category = _category_for_path(path, extractor)
    if category is None:
        _warn(stderr, record_number, "extractor has no category", record)
        return [], True

    try:
        content_bytes = content.encode("utf-8")
    except UnicodeEncodeError:
        _warn(stderr, record_number, "content is not valid UTF-8", record)
        return [], True
    if len(content_bytes) > MAX_CONTENT_BYTES:
        _warn(stderr, record_number, "content is too large", record)
        return [], True

    try:
        source = _source_url(repo_name, path)
        discovered_urls = extract_registry_urls(content, extractor)
        if not isinstance(discovered_urls, list):
            raise TypeError("extractor returned a non-list result")
    except Exception as error:  # noqa: BLE001 - untrusted record boundary
        _warn(
            stderr,
            record_number,
            f"extraction failed ({type(error).__name__})",
            record,
        )
        return [], True

    try:
        source_role = _source_role(path)
        content_sha256 = hashlib.sha256(content_bytes).hexdigest()
        observations: list[dict[str, str]] = []
        for discovered_url in discovered_urls:
            if not isinstance(discovered_url, str) or not discovered_url:
                continue
            observations.append(
                {
                    "category": category,
                    "discovered_url": discovered_url,
                    "query_id": QUERY_ID,
                    "extractor": extractor,
                    "source": source,
                    "source_kind": SOURCE_KIND,
                    "source_path": path,
                    "source_role": source_role,
                    "repository": repo_name,
                    "content_sha256": content_sha256,
                }
            )
    except Exception as error:  # noqa: BLE001 - untrusted record boundary
        _warn(
            stderr,
            record_number,
            f"observation construction failed ({type(error).__name__})",
            record,
        )
        return [], True
    return observations, False


def collect_seed_observations(
    records: Iterable[Any],
    *,
    stderr: TextIO | None = None,
) -> SeedImportResult:
    """Extract observations from already iterable seed records.

    Mapping objects are treated as decoded records. String and bytes values
    are treated as raw JSONL lines, which keeps this helper useful for tests
    and for callers that already have a line iterator.
    """

    warning_stream = _warning_stream(stderr)
    observations: list[dict[str, str]] = []
    records_read = 0
    skipped = 0
    for records_read, item in enumerate(records, start=1):
        record: Any = item
        if isinstance(item, (bytes, str)):
            record, was_skipped = _decode_json_line(
                item,
                record_number=records_read,
                stderr=warning_stream,
            )
            if was_skipped:
                skipped += 1
                continue
        produced, was_skipped = _record_observations(
            record,
            record_number=records_read,
            stderr=warning_stream,
        )
        observations.extend(produced)
        skipped += int(was_skipped)
    if skipped:
        print(
            f"Seed import skipped {skipped} record(s); see warnings above.",
            file=warning_stream,
        )
    return SeedImportResult(
        observations=observations,
        records_read=records_read,
        skipped=skipped,
    )


def _bounded_lines(stream: BinaryIO) -> Iterable[tuple[bytes, bool]]:
    """Yield complete lines without materializing an unbounded JSON record."""

    while True:
        line = stream.readline(MAX_RECORD_BYTES + 1)
        if not line:
            return
        if len(line) <= MAX_RECORD_BYTES:
            yield line, False
            continue

        # Consume the rest of this physical record so its tail cannot be
        # mistaken for a second record. ``readline`` keeps each chunk bounded.
        while b"\n" not in line:
            line = stream.readline(MAX_RECORD_BYTES + 1)
            if not line:
                break
        yield b"", True


def read_seed_records(
    path: Path,
    *,
    stderr: TextIO | None = None,
) -> SeedImportResult:
    """Read an uncompressed or ``.gz`` newline-delimited JSON seed file."""

    seed_path = Path(path)
    try:
        if seed_path.suffix.casefold() == ".gz":
            stream = gzip.open(seed_path, "rb")
        else:
            stream = seed_path.open("rb")
            if stream.read(2) == b"\x1f\x8b":
                stream.close()
                stream = gzip.open(seed_path, "rb")
            else:
                stream.seek(0)
    except OSError as error:
        raise SeedImportError(f"cannot open seed file {seed_path}: {error}") from error

    warning_stream = _warning_stream(stderr)
    observations: list[dict[str, str]] = []
    records_read = 0
    skipped = 0
    try:
        with stream:
            for records_read, (line, too_large) in enumerate(
                _bounded_lines(stream),
                start=1,
            ):
                if too_large:
                    _warn(warning_stream, records_read, "record is too large")
                    skipped += 1
                    continue
                record, was_skipped = _decode_json_line(
                    line.rstrip(b"\r\n"),
                    record_number=records_read,
                    stderr=warning_stream,
                )
                if was_skipped:
                    skipped += 1
                    continue
                produced, was_skipped = _record_observations(
                    record,
                    record_number=records_read,
                    stderr=warning_stream,
                )
                observations.extend(produced)
                skipped += int(was_skipped)
    except (OSError, EOFError) as error:
        raise SeedImportError(f"cannot read seed file {seed_path}: {error}") from error

    if skipped:
        print(
            f"Seed import skipped {skipped} record(s); see warnings above.",
            file=warning_stream,
        )
    return SeedImportResult(
        observations=observations,
        records_read=records_read,
        skipped=skipped,
    )


def apply_repository_threshold(
    observations: Iterable[dict[str, str]],
    *,
    minimum_repositories: int = DEFAULT_MINIMUM_REPOSITORIES,
    known_targets: Iterable[str] = (),
) -> tuple[list[dict[str, str]], set[str]]:
    """Admit a seed-only hostname only once it spans independent repositories.

    Repetition inside a single repository proves nothing, so reach is counted
    over distinct repository names. A target another discovery path already
    knows keeps its evidence regardless: it has been vetted elsewhere, and
    discarding the seed's corroboration would lose information.
    """

    observation_list = list(observations)
    known = set(known_targets)
    repositories: dict[str, set[str]] = {}
    for observation in observation_list:
        target = observation.get("target")
        repository = observation.get("repository")
        if isinstance(target, str) and isinstance(repository, str):
            repositories.setdefault(target, set()).add(repository)

    dropped: set[str] = set()
    kept: list[dict[str, str]] = []
    for observation in observation_list:
        target = observation.get("target")
        if not isinstance(target, str):
            continue
        if target in known:
            kept.append(observation)
            continue
        if len(repositories.get(target, set())) < minimum_repositories:
            dropped.add(target)
            continue
        kept.append(observation)
    return kept, dropped


def _rejected_targets(document: Any) -> set[str]:
    if not isinstance(document, dict) or not isinstance(
        document.get("rejections"), list
    ):
        return set()
    return {
        item["target"]
        for item in document["rejections"]
        if isinstance(item, dict) and isinstance(item.get("target"), str)
    }


def _candidate_targets(document: Any) -> set[str]:
    if not isinstance(document, dict) or not isinstance(
        document.get("candidates"), list
    ):
        return set()
    return {
        item["target"]
        for item in document["candidates"]
        if isinstance(item, dict) and isinstance(item.get("target"), str)
    }


def _filter_seed_observations(
    observations: list[dict[str, str]],
    *,
    exclusions: Any,
    catalog_entries: Iterable[dict[str, Any]],
    rejected_targets: Iterable[str],
    stderr: TextIO,
) -> tuple[list[dict[str, str]], int]:
    """Run the shared filter while containing an invalid extracted URL."""

    catalog_entry_list = list(catalog_entries)
    rejected_target_set = set(rejected_targets)
    try:
        return (
            filter_observations(
                observations,
                exclusions=exclusions,
                catalog_entries=catalog_entry_list,
                rejected_targets=rejected_target_set,
            ),
            0,
        )
    except Exception as error:  # noqa: BLE001 - untrusted observation boundary
        # ``filter_observations`` normally drops malformed targets itself. A
        # URL containing characters rejected by urllib before TargetError is
        # raised can still escape that helper; retry one observation at a time
        # so it cannot discard or abort the rest of this seed.
        print(
            "Seed filtering encountered an invalid observation; "
            f"recovering individually ({type(error).__name__}).",
            file=stderr,
        )

    filtered: list[dict[str, str]] = []
    filtering_failures = 0
    for observation_number, observation in enumerate(observations, start=1):
        try:
            filtered.extend(
                filter_observations(
                    [observation],
                    exclusions=exclusions,
                    catalog_entries=catalog_entry_list,
                    rejected_targets=rejected_target_set,
                )
            )
        except Exception as error:  # noqa: BLE001 - untrusted observation boundary
            filtering_failures += 1
            _warn(
                stderr,
                observation_number,
                f"filtering failed ({type(error).__name__})",
                {
                    "repo_name": observation.get("repository", ""),
                    "path": observation.get("source_path", ""),
                },
            )
    return filtered, filtering_failures


def run_seed_import(
    root: Path,
    seed_path: Path,
    *,
    dry_run: bool = False,
    minimum_repositories: int = DEFAULT_MINIMUM_REPOSITORIES,
    stderr: TextIO | None = None,
) -> SeedImportResult:
    """Import a seed and merge its filtered observations into candidates."""

    repository_root = Path(root)
    imported = read_seed_records(Path(seed_path), stderr=stderr)

    category_ids = {item["id"] for item in load_categories(repository_root)}
    unknown_categories = {
        observation["category"]
        for observation in imported.observations
        if observation["category"] not in category_ids
    }
    if unknown_categories:
        raise SeedImportError(
            "seed importer has unknown category ids: "
            + ", ".join(sorted(unknown_categories))
        )

    exclusions = read_json(repository_root / "data" / "discovery_exclusions.json")
    rejections = read_json(repository_root / "data" / "rejections.json")
    catalog = load_catalog(repository_root)
    filtered, filtering_failures = _filter_seed_observations(
        imported.observations,
        exclusions=exclusions,
        catalog_entries=catalog["entries"],
        rejected_targets=_rejected_targets(rejections),
        stderr=_warning_stream(stderr),
    )

    candidates_path = repository_root / "data" / "candidates.json"
    current = read_json(candidates_path)

    # Reach is judged only against hosts this seed introduces. A target another
    # discovery path already surfaced has been vetted by that path, so its seed
    # corroboration is kept regardless of how many repositories carry it here.
    admitted, below_threshold = apply_repository_threshold(
        filtered,
        minimum_repositories=minimum_repositories,
        known_targets=_candidate_targets(current),
    )
    if below_threshold:
        print(
            f"Seed withheld {len(below_threshold)} hostname(s) seen in fewer "
            f"than {minimum_repositories} distinct repositories.",
            file=_warning_stream(stderr),
        )

    merged, _ = merge_candidates(current, admitted)
    # merge_candidates returns the canonical candidates shape. Preserve
    # metadata owned by the existing discovery pipeline, especially its rules
    # fingerprint, because this offline source does not refresh those rules.
    for key, value in current.items():
        if key != "candidates":
            merged[key] = value

    candidates_added = len(_candidate_targets(merged) - _candidate_targets(current))
    result = SeedImportResult(
        observations=imported.observations,
        records_read=imported.records_read,
        skipped=imported.skipped + filtering_failures,
        candidates_added=candidates_added,
    )
    if not dry_run and merged != current:
        write_json_atomic(candidates_path, merged)
        # reviews/pending is generated from the candidates file, and
        # scripts/validate.py fails when it drifts. Refresh it here for the
        # same reason scripts/promote.py regenerates dist/.
        write_review_queue(repository_root)
    return result


load_seed_records = read_seed_records
import_seed = run_seed_import

#!/usr/bin/env python3
"""Validate source data and prove generated files are current."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import load_catalog, load_categories, read_json, validate_documents
from url_lists.discovery import SOURCE_ROLES
from url_lists.extractors import SUPPORTED_EXTRACTORS
from url_lists.llm_review import validate_review_files
from url_lists.normalize import TargetError, normalize_target


def validate_candidates(document: dict[str, Any], category_ids: set[str]) -> list[str]:
    problems: list[str] = []
    if document.get("schema_version") != 1:
        return ["unsupported candidates schema version"]
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        return ["candidates must be a list"]
    rules_sha256 = document.get("discovery_rules_sha256")
    if rules_sha256 is not None and not (
        isinstance(rules_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", rules_sha256)
    ):
        problems.append("candidates discovery rules SHA-256 is invalid")

    seen: set[str] = set()
    for index, candidate in enumerate(candidates, start=1):
        label = f"candidate {index}"
        if not isinstance(candidate, dict):
            problems.append(f"{label} must be an object")
            continue
        target = candidate.get("target")
        try:
            normalized = normalize_target(target, preserve_path=False)
        except (TargetError, TypeError) as error:
            problems.append(f"{label} has invalid target: {error}")
            continue
        if target != normalized:
            problems.append(f"{label} target is not normalized: {target}")
        if target in seen:
            problems.append(f"{label} duplicates target: {target}")
        seen.add(target)
        categories = candidate.get("categories")
        if not isinstance(categories, list) or not categories:
            problems.append(f"{label} has no categories")
        elif set(categories) - category_ids:
            problems.append(f"{label} has unknown categories")
        if candidate.get("confidence") not in {"low", "medium", "high"}:
            problems.append(f"{label} has invalid confidence")
        review_flags = candidate.get("review_flags")
        if not isinstance(review_flags, list) or not all(
            flag in {
                "documentation-like",
                "non-configuration-evidence-only",
                "nonstandard-port",
                "placeholder-like",
                "retired-service",
            }
            for flag in review_flags
        ):
            problems.append(f"{label} has invalid review flags")
        sources = candidate.get("sources")
        if not isinstance(sources, list) or not sources:
            problems.append(f"{label} has no evidence sources")
        else:
            for source in sources:
                if (
                    not isinstance(source, dict)
                    or not isinstance(source.get("source"), str)
                    or not source["source"].startswith("https://")
                    or not isinstance(source.get("source_kind"), str)
                    or not isinstance(source.get("repository"), str)
                ):
                    problems.append(f"{label} has an invalid evidence source")
                    break
                optional_strings = ("extractor", "query_id", "source_path")
                if any(
                    key in source
                    and (
                        not isinstance(source[key], str)
                        or not source[key].strip()
                    )
                    for key in optional_strings
                ):
                    problems.append(f"{label} has invalid evidence provenance")
                    break
                if (
                    "source_role" in source
                    and source["source_role"] not in SOURCE_ROLES
                ):
                    problems.append(f"{label} has an invalid evidence source role")
                    break
                content_sha256 = source.get("content_sha256")
                if content_sha256 is not None and not (
                    isinstance(content_sha256, str)
                    and re.fullmatch(r"[0-9a-f]{64}", content_sha256)
                ):
                    problems.append(f"{label} has an invalid evidence content hash")
                    break
    return problems


def validate_rejections(
    document: dict[str, Any],
    category_ids: set[str],
    candidate_targets: set[str],
) -> list[str]:
    problems: list[str] = []
    if document.get("schema_version") != 1:
        return ["unsupported rejections schema version"]
    rejections = document.get("rejections")
    if not isinstance(rejections, list):
        return ["rejections must be a list"]

    seen: set[str] = set()
    for index, rejection in enumerate(rejections, start=1):
        label = f"rejection {index}"
        if not isinstance(rejection, dict):
            problems.append(f"{label} must be an object")
            continue
        target = rejection.get("target")
        try:
            normalized = normalize_target(target, preserve_path=False)
        except (TargetError, TypeError) as error:
            problems.append(f"{label} has invalid target: {error}")
            continue
        if target != normalized:
            problems.append(f"{label} target is not normalized")
        if target in seen:
            problems.append(f"{label} duplicates target: {target}")
        if target in candidate_targets:
            problems.append(f"{label} is still present as a candidate")
        seen.add(target)
        categories = rejection.get("categories")
        if (
            not isinstance(categories, list)
            or not categories
            or set(categories) - category_ids
        ):
            problems.append(f"{label} has invalid categories")
        if not isinstance(rejection.get("reason"), str) or not rejection["reason"].strip():
            problems.append(f"{label} has no reason")
        sources = rejection.get("sources")
        if not isinstance(sources, list) or not sources:
            problems.append(f"{label} has no preserved evidence")
    return problems


def validate_discovery_configuration(category_ids: set[str]) -> list[str]:
    problems: list[str] = []
    search = read_json(ROOT / "data" / "search_queries.json")
    if search.get("schema_version") != 1 or not isinstance(search.get("queries"), list):
        problems.append("search query configuration has an unsupported schema")
    else:
        seen_query_ids: set[str] = set()
        for index, query in enumerate(search["queries"], start=1):
            label = f"search query {index}"
            if not isinstance(query, dict):
                problems.append(f"{label} must be an object")
                continue
            if query.get("ecosystem") not in category_ids:
                problems.append(f"{label} has an unknown ecosystem")
            query_id = query.get("id")
            if not isinstance(query_id, str) or not re.fullmatch(
                r"[a-z0-9]+(?:-[a-z0-9]+)*", query_id
            ):
                problems.append(f"{label} has an invalid ID")
            elif query_id in seen_query_ids:
                problems.append(f"{label} duplicates ID {query_id}")
            else:
                seen_query_ids.add(query_id)
            if not isinstance(query.get("query"), str) or not query["query"].strip():
                problems.append(f"{label} has no query text")
            if "context_terms" in query:
                problems.append(f"{label} still uses broad context terms")
            extractor = query.get("extractor")
            if extractor not in SUPPORTED_EXTRACTORS:
                problems.append(f"{label} has an unsupported extractor")
            keys = query.get("keys")
            if extractor == "environment-assignment":
                if (
                    not isinstance(keys, list)
                    or not keys
                    or not all(isinstance(item, str) and item for item in keys)
                    or len(keys) != len(set(keys))
                ):
                    problems.append(f"{label} has invalid assignment keys")
            elif keys is not None:
                problems.append(f"{label} has unexpected assignment keys")
            maximum = query.get("max_results")
            if not isinstance(maximum, int) or not 1 <= maximum <= 100:
                problems.append(f"{label} max_results must be between 1 and 100")

    exclusions = read_json(ROOT / "data" / "discovery_exclusions.json")
    if exclusions.get("schema_version") != 1:
        problems.append("discovery exclusions have an unsupported schema")
    for key in ("exact_hosts", "suffixes", "shared_hosts"):
        values = exclusions.get(key)
        if (
            not isinstance(values, list)
            or not all(isinstance(item, str) and item for item in values)
        ):
            problems.append(f"discovery exclusions field {key} is invalid")
    return problems


def main() -> int:
    categories = load_categories(ROOT)
    load_catalog(ROOT)
    category_ids = {item["id"] for item in categories}
    candidates_document = read_json(ROOT / "data" / "candidates.json")
    problems = validate_candidates(
        candidates_document,
        category_ids,
    )
    problems.extend(
        validate_rejections(
            read_json(ROOT / "data" / "rejections.json"),
            category_ids,
            {
                candidate.get("target")
                for candidate in candidates_document.get("candidates", [])
                if isinstance(candidate, dict)
            },
        )
    )
    problems.extend(validate_discovery_configuration(category_ids))
    problems.extend(validate_documents(ROOT))
    problems.extend(validate_review_files(ROOT))
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    print("Catalog, candidates, and generated files are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

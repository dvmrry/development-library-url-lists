#!/usr/bin/env python3
"""Validate source data and prove generated files are current."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import load_catalog, load_categories, read_json, validate_documents
from url_lists.normalize import TargetError, normalize_target


def validate_candidates(document: dict[str, Any], category_ids: set[str]) -> list[str]:
    problems: list[str] = []
    if document.get("schema_version") != 1:
        return ["unsupported candidates schema version"]
    candidates = document.get("candidates")
    if not isinstance(candidates, list):
        return ["candidates must be a list"]

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
        sources = candidate.get("sources")
        if not isinstance(sources, list) or not sources:
            problems.append(f"{label} has no evidence sources")
        elif any(
            not isinstance(source, dict)
            or not isinstance(source.get("source"), str)
            or not source["source"].startswith("https://")
            or not isinstance(source.get("source_kind"), str)
            or not isinstance(source.get("repository"), str)
            for source in sources
        ):
            problems.append(f"{label} has an invalid evidence source")
    return problems


def validate_discovery_configuration(category_ids: set[str]) -> list[str]:
    problems: list[str] = []
    search = read_json(ROOT / "data" / "search_queries.json")
    if search.get("schema_version") != 1 or not isinstance(search.get("queries"), list):
        problems.append("search query configuration has an unsupported schema")
    else:
        for index, query in enumerate(search["queries"], start=1):
            label = f"search query {index}"
            if not isinstance(query, dict):
                problems.append(f"{label} must be an object")
                continue
            if query.get("ecosystem") not in category_ids:
                problems.append(f"{label} has an unknown ecosystem")
            if not isinstance(query.get("query"), str) or not query["query"].strip():
                problems.append(f"{label} has no query text")
            context_terms = query.get("context_terms")
            if (
                not isinstance(context_terms, list)
                or not context_terms
                or not all(isinstance(item, str) and item for item in context_terms)
            ):
                problems.append(f"{label} has invalid context terms")
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
    problems = validate_candidates(
        read_json(ROOT / "data" / "candidates.json"),
        category_ids,
    )
    problems.extend(validate_discovery_configuration(category_ids))
    problems.extend(validate_documents(ROOT))
    if problems:
        for problem in problems:
            print(f"ERROR: {problem}", file=sys.stderr)
        return 1
    print("Catalog, candidates, and generated files are valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

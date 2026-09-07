#!/usr/bin/env python3
"""Promote a reviewed discovery into the curated catalog."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import (
    load_catalog,
    load_categories,
    read_json,
    write_json_atomic,
)
from url_lists.normalize import TargetError, normalize_target
from url_lists.outputs import refresh_outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument(
        "--category",
        action="append",
        dest="categories",
        help="category id; repeat to assign more than one",
    )
    parser.add_argument(
        "--match",
        choices=("exact", "path", "suffix"),
        default="exact",
    )
    parser.add_argument("--kind", default="discovered-repository")
    parser.add_argument(
        "--extend",
        action="store_true",
        help="add reviewed categories to an existing target with the same match mode",
    )
    parser.add_argument(
        "--review-note",
        help="record evidence and blocking-scope rationale; required for stale evidence",
    )
    parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="HTTP(S) evidence URL; required if target is not a candidate",
    )
    arguments = parser.parse_args()
    if arguments.review_note is not None and (
        not arguments.review_note.strip() or arguments.review_note.startswith("REPLACE")
    ):
        parser.error("--review-note must contain your actual review rationale")

    try:
        target = normalize_target(
            arguments.target,
            preserve_path=arguments.match == "path",
        )
    except TargetError as error:
        parser.error(str(error))
    if arguments.match == "suffix" and not target.startswith("."):
        parser.error("suffix targets require a leading dot")
    if arguments.match != "suffix" and target.startswith("."):
        parser.error("leading-dot targets require --match suffix")
    if arguments.match == "path" and "/" not in target:
        parser.error("path matches require a URL path")
    if not arguments.kind.strip():
        parser.error("--kind cannot be empty")

    categories = {item["id"] for item in load_categories(ROOT)}
    candidates_path = ROOT / "data" / "candidates.json"
    candidates_document = read_json(candidates_path)
    candidate = next(
        (
            item
            for item in candidates_document["candidates"]
            if item["target"] == target
        ),
        None,
    )

    selected_categories = set(arguments.categories or [])
    if not selected_categories and candidate is not None:
        selected_categories.update(candidate["categories"])
    if not selected_categories:
        parser.error("--category is required when target is not a candidate")
    unknown = selected_categories - categories
    if unknown:
        parser.error(f"unknown category ids: {', '.join(sorted(unknown))}")

    evidence = set(arguments.evidence)
    if candidate is not None:
        if (
            any(source.get("needs_revalidation") for source in candidate["sources"])
            and not arguments.review_note
        ):
            parser.error(
                "evidence needs revalidation; inspect it and record --review-note before promotion"
            )
        evidence.update(source["source"] for source in candidate["sources"])
    if not evidence or not all(
        url.startswith(("https://", "http://")) for url in evidence
    ):
        parser.error("at least one HTTP(S) evidence URL is required")

    catalog = load_catalog(ROOT)
    existing = next(
        (
            item
            for item in catalog["entries"]
            if item["target"] == target and item["match"] == arguments.match
        ),
        None,
    )
    if existing and not arguments.extend:
        parser.error("target and match mode already exist in the catalog")
    if arguments.extend and (existing is None or existing["status"] != "approved"):
        parser.error("--extend requires an approved target with the same match mode")
    if existing:
        if not selected_categories - set(existing["categories"]):
            parser.error("the selected categories are already approved")
        existing["categories"] = sorted(
            set(existing["categories"]) | selected_categories
        )
        existing["evidence"] = sorted(set(existing["evidence"]) | evidence)
        entry = existing
    else:
        entry = {
            "target": target,
            "match": arguments.match,
            "categories": sorted(selected_categories),
            "kind": arguments.kind,
            "status": "approved",
            "evidence": sorted(evidence),
        }
        catalog["entries"].append(entry)
    if arguments.review_note:
        entry.setdefault("reviews", []).append(
            {
                "reviewed_on": datetime.now(timezone.utc).date().isoformat(),
                "categories": sorted(selected_categories),
                "note": arguments.review_note.strip(),
            }
        )
    catalog["entries"].sort(
        key=lambda item: (item["target"].lstrip("."), item["match"])
    )
    write_json_atomic(ROOT / "data" / "catalog.json", catalog)

    if candidate is not None:
        remaining = set(candidate["categories"]) - set(entry["categories"])
        if remaining:
            candidate["categories"] = sorted(remaining)
        else:
            candidates_document["candidates"] = [
                item
                for item in candidates_document["candidates"]
                if item["target"] != target
            ]
        write_json_atomic(candidates_path, candidates_document)

    refresh_outputs(ROOT)
    print(f"Promoted {target} to {', '.join(sorted(selected_categories))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

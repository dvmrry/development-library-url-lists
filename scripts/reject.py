#!/usr/bin/env python3
"""Reject and suppress a reviewed discovery candidate."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import read_json, write_json_atomic
from url_lists.normalize import TargetError, normalize_target


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("target")
    parser.add_argument("--reason", required=True)
    arguments = parser.parse_args()

    try:
        target = normalize_target(arguments.target, preserve_path=False)
    except TargetError as error:
        parser.error(str(error))
    reason = arguments.reason.strip()
    if not reason:
        parser.error("--reason cannot be empty")

    candidates_path = ROOT / "data" / "candidates.json"
    candidates = read_json(candidates_path)
    candidate = next(
        (item for item in candidates["candidates"] if item["target"] == target),
        None,
    )
    if candidate is None:
        parser.error("target is not present in data/candidates.json")

    rejections_path = ROOT / "data" / "rejections.json"
    rejections = read_json(rejections_path)
    if any(item["target"] == target for item in rejections["rejections"]):
        parser.error("target is already rejected")

    rejections["rejections"].append(
        {
            "target": target,
            "categories": candidate["categories"],
            "reason": reason,
            "rejected_on": datetime.now(timezone.utc).date().isoformat(),
            "sources": candidate["sources"],
        }
    )
    rejections["rejections"].sort(key=lambda item: item["target"])
    candidates["candidates"] = [
        item for item in candidates["candidates"] if item["target"] != target
    ]
    write_json_atomic(rejections_path, rejections)
    write_json_atomic(candidates_path, candidates)
    print(f"Rejected and suppressed {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

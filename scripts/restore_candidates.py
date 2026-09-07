#!/usr/bin/env python3
"""Combine fetched automation evidence with the checked-out candidate snapshot."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import read_json, write_json_atomic
from url_lists.discovery import merge_candidate_snapshots


def main() -> int:
    content = subprocess.run(
        ["git", "show", "FETCH_HEAD:data/candidates.json"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    path = ROOT / "data" / "candidates.json"
    merged = merge_candidate_snapshots(read_json(path), json.loads(content))
    write_json_atomic(path, merged)
    print(f"Restored evidence; {len(merged['candidates'])} combined candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compare a sanitized JSONL traffic sample locally; no network requests."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import load_catalog, write_json_atomic
from url_lists.traffic_review import review_traffic


def records(path: Path):
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                yield None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", type=Path)
    parser.add_argument(
        "--output", type=Path, default=ROOT / ".private/traffic-review.json"
    )
    arguments = parser.parse_args()
    report = review_traffic(records(arguments.sample), load_catalog(ROOT))
    write_json_atomic(arguments.output, report)
    print(
        f"{report['covered_requests']} covered / {report['uncovered_requests']} uncovered requests; "
        f"{report['invalid_records']} invalid rows. Report: {arguments.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

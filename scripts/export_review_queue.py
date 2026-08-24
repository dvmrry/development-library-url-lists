#!/usr/bin/env python3
"""Export candidates for private Cloudflare and Zscaler review."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.review_queue import write_review_queue


def main() -> int:
    document = write_review_queue(ROOT)
    print(f"Exported {document['candidate_count']} candidate domain(s) for private review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

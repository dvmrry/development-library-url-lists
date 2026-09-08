#!/usr/bin/env python3
"""Render deterministic distribution files from the curated catalog."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.outputs import refresh_outputs


def main() -> int:
    refresh_outputs(ROOT)
    print("Rendered dist/ and reviews/pending/ from source data")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

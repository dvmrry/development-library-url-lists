#!/usr/bin/env python3
"""Render deterministic distribution files from the curated catalog."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import write_documents


def main() -> int:
    write_documents(ROOT)
    print("Rendered dist/ from data/catalog.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

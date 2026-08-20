#!/usr/bin/env python3
"""Run optional network discovery and refresh generated files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import write_documents
from url_lists.discovery import DiscoveryError, run_network_discovery


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--network",
        action="store_true",
        help="query trusted free sources before rendering",
    )
    arguments = parser.parse_args()

    additions = 0
    if arguments.network:
        try:
            additions = run_network_discovery(ROOT)
        except DiscoveryError as error:
            print(f"Discovery failed: {error}", file=sys.stderr)
            return 1
    write_documents(ROOT)
    print(f"Update complete; {additions} new evidence record(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

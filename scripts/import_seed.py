#!/usr/bin/env python3
"""Import an offline BigQuery GitHub seed into discovery candidates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import CatalogError
from url_lists.discovery import DiscoveryError
from url_lists.seed_import import (
    DEFAULT_MINIMUM_REPOSITORIES,
    SeedImportError,
    run_seed_import,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("seed_file", type=Path)
    parser.add_argument(
        "--min-repositories",
        type=int,
        default=DEFAULT_MINIMUM_REPOSITORIES,
        help=(
            "distinct public repositories a seed-only hostname must appear in "
            "before it is admitted for review"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the import without writing data/candidates.json",
    )
    arguments = parser.parse_args()

    try:
        result = run_seed_import(
            ROOT,
            arguments.seed_file,
            dry_run=arguments.dry_run,
            minimum_repositories=arguments.min_repositories,
        )
    except (CatalogError, DiscoveryError, OSError, SeedImportError) as error:
        print(f"Seed import failed: {error}", file=sys.stderr)
        return 1

    mode = "Dry run" if arguments.dry_run else "Import"
    write_status = "no files written; " if arguments.dry_run else ""
    print(
        f"{mode} complete; "
        f"{write_status}"
        f"records read: {result.records_read}; "
        f"skipped: {result.skipped}; "
        f"observations produced: {result.observations_produced}; "
        f"candidates added: {result.candidates_added}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

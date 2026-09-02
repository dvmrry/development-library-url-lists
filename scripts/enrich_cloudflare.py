#!/usr/bin/env python3
"""Enrich discovery candidates with cached Cloudflare Domain Intelligence."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.cloudflare_intel import (
    DEFAULT_MAX_CALLS,
    DEFAULT_STALE_DAYS,
    CloudflareIntelError,
    enrich_candidates,
    skipped_report,
    write_review,
)


def _workflow_warning(message: str) -> None:
    safe = "".join(character if character.isprintable() else "?" for character in message)
    safe = safe.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=Cloudflare Intel enrichment::{safe[:500]}")
    else:
        print(f"WARNING: {safe[:500]}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--optional", action="store_true")
    parser.add_argument("--max-calls", type=int, default=DEFAULT_MAX_CALLS)
    parser.add_argument("--stale-days", type=int, default=DEFAULT_STALE_DAYS)
    arguments = parser.parse_args()

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "")
    if not account_id or not token:
        message = "Cloudflare credentials are not configured"
        write_review(ROOT, skipped_report(ROOT, message))
        if arguments.optional:
            _workflow_warning(message)
            return 0
        print(message, file=sys.stderr)
        return 1

    try:
        report = enrich_candidates(
            ROOT,
            account_id=account_id,
            token=token,
            max_calls=arguments.max_calls,
            stale_days=arguments.stale_days,
        )
    except CloudflareIntelError as error:
        report = skipped_report(ROOT, str(error))
        report["status"] = "error"
        write_review(ROOT, report)
        _workflow_warning(str(error))
        return 0 if arguments.optional else 1

    write_review(ROOT, report)
    if report.get("provider_error"):
        _workflow_warning(report["provider_error"])
        return 0 if arguments.optional else 1
    print(
        "Cloudflare enrichment "
        f"{report['status']}: {report['refreshed_domain_count']} refreshed, "
        f"{report['remaining_domain_count']} pending"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run an optional, suggestion-only LLM coverage review."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.llm_review import (
    DEFAULT_MODELS,
    PROVIDER_API_KEYS,
    ReviewError,
    create_review_report,
    write_review_report,
)


def _warning(message: str) -> None:
    safe = message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::warning title=Optional LLM coverage review::{safe}")
    else:
        print(f"Optional LLM coverage review skipped: {message}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--provider",
        choices=["disabled", *sorted(DEFAULT_MODELS)],
        default=os.environ.get("LLM_REVIEW_PROVIDER", "disabled").strip().lower()
        or "disabled",
        help="hosted provider to call; defaults to LLM_REVIEW_PROVIDER",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("LLM_REVIEW_MODEL", "").strip(),
        help="optional provider model override",
    )
    parser.add_argument(
        "--optional",
        action="store_true",
        help="fail open when the provider is disabled, unavailable, or invalid",
    )
    arguments = parser.parse_args()

    if arguments.provider == "disabled":
        print("Optional LLM coverage review is disabled")
        return 0

    provider = arguments.provider
    model = arguments.model or DEFAULT_MODELS[provider]
    key_name = PROVIDER_API_KEYS[provider]
    api_key = os.environ.get(key_name, "")
    try:
        report = create_review_report(ROOT, provider, model, api_key)
        write_review_report(ROOT, report)
    except ReviewError as error:
        if arguments.optional:
            _warning(str(error))
            return 0
        print(f"LLM coverage review failed: {error}", file=sys.stderr)
        return 1

    print(
        f"LLM coverage review complete: {len(report['findings'])} suggestion(s) "
        f"from {provider}/{model}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

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
    PROMPT_VERSION,
    build_review_input,
    review_input_sha256,
    validate_review_files,
)
from url_lists.catalog import CatalogError, read_json


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
    parser.add_argument(
        "--force",
        action="store_true",
        help="review even when the input and model are unchanged",
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
        previous_path = ROOT / "reviews" / "llm" / "latest.json"
        if (
            not arguments.force
            and previous_path.exists()
            and not validate_review_files(ROOT)
        ):
            previous = read_json(previous_path)
            if (
                previous.get("provider") == provider
                and previous.get("model") == model
                and previous.get("prompt_version") == PROMPT_VERSION
                and previous.get("input_sha256")
                == review_input_sha256(build_review_input(ROOT))
            ):
                print(
                    "LLM review reused: inventory, prompt, provider, and model are unchanged"
                )
                return 0
        report = create_review_report(ROOT, provider, model, api_key)
        write_review_report(ROOT, report)
    except (ReviewError, CatalogError) as error:
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

"""Deterministic public handoff for private Cloudflare and Zscaler review."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

from .catalog import read_json, write_json_atomic
from .normalize import TargetError, target_hostname


QUEUE_JSON = Path("reviews/pending/queue.json")
QUEUE_TEXT = Path("reviews/pending/domains.txt")


def build_review_queue(root: Path) -> dict[str, Any]:
    candidates = read_json(root / "data" / "candidates.json").get("candidates", [])
    entries = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            domain = target_hostname(candidate["target"])
        except (KeyError, TargetError):
            continue
        sources = candidate.get("sources", [])
        entries.append(
            {
                "domain": domain,
                "target": candidate["target"],
                "categories": sorted(set(candidate.get("categories", []))),
                "confidence": candidate.get("confidence"),
                "review_flags": sorted(set(candidate.get("review_flags", []))),
                "source_kinds": sorted(
                    {
                        source.get("source_kind")
                        for source in sources
                        if isinstance(source, dict)
                        and isinstance(source.get("source_kind"), str)
                    }
                ),
                "source_ecosystems": sorted(
                    {
                        source.get("source_ecosystem")
                        for source in sources
                        if isinstance(source, dict)
                        and isinstance(source.get("source_ecosystem"), str)
                    }
                ),
                "source_roles": sorted(
                    {
                        source.get("source_role")
                        for source in sources
                        if isinstance(source, dict)
                        and isinstance(source.get("source_role"), str)
                    }
                ),
            }
        )
    entries.sort(
        key=lambda entry: (
            {"high": 0, "medium": 1, "low": 2}.get(entry["confidence"], 3),
            entry["domain"],
        )
    )
    return {
        "schema_version": 1,
        "source": "data/candidates.json",
        "candidate_count": len(entries),
        "entries": entries,
    }


def _write_text_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        text=True,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
        os.replace(temporary_name, path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def write_review_queue(root: Path) -> dict[str, Any]:
    document = build_review_queue(root)
    write_json_atomic(root / QUEUE_JSON, document)
    domains = sorted({entry["domain"] for entry in document["entries"]})
    _write_text_atomic(root / QUEUE_TEXT, "".join(f"{domain}\n" for domain in domains))
    return document


def validate_review_queue(root: Path) -> list[str]:
    expected = build_review_queue(root)
    json_path = root / QUEUE_JSON
    text_path = root / QUEUE_TEXT
    problems = []
    if not json_path.exists():
        problems.append(f"missing generated file: {QUEUE_JSON.as_posix()}")
    elif read_json(json_path) != expected:
        problems.append(f"stale generated file: {QUEUE_JSON.as_posix()}")
    expected_domains = "".join(
        f"{domain}\n" for domain in sorted({entry["domain"] for entry in expected["entries"]})
    )
    if not text_path.exists():
        problems.append(f"missing generated file: {QUEUE_TEXT.as_posix()}")
    elif text_path.read_text(encoding="utf-8") != expected_domains:
        problems.append(f"stale generated file: {QUEUE_TEXT.as_posix()}")
    return problems

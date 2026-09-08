"""Deterministic public handoff for private Cloudflare and Zscaler review."""

from __future__ import annotations

import os
import tempfile
import html
import shlex
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .catalog import read_json, write_json_atomic
from .discovery import _is_covered
from .normalize import TargetError, target_hostname


QUEUE_JSON = Path("reviews/pending/queue.json")
QUEUE_TEXT = Path("reviews/pending/domains.txt")
QUEUE_MARKDOWN = Path("reviews/pending/README.md")


def evidence_reach(sources: list[dict[str, Any]]) -> dict[str, int]:
    code = [
        s for s in sources if s.get("source_kind") in {"github-code", "bigquery-github"}
    ]
    repositories = {s["repository"].lower() for s in code if s.get("repository")}
    return {
        "repository_count": len(repositories),
        "owner_count": len({name.split("/", 1)[0] for name in repositories}),
        "content_count": len(
            {s["content_sha256"] for s in code if s.get("content_sha256")}
        ),
    }


def balanced_entries(
    entries: list[dict[str, Any]], limit: int | None = 20
) -> list[dict[str, Any]]:
    """Round-robin ranked ecosystems without reviewing a target twice."""
    groups: dict[str, deque] = defaultdict(deque)
    for entry in entries:
        for category in entry["categories"] or ["uncategorized"]:
            groups[category].append(entry)
    selected, seen = [], set()
    while any(groups.values()) and (limit is None or len(selected) < limit):
        for category in sorted(groups):
            while groups[category] and groups[category][0]["target"] in seen:
                groups[category].popleft()
            if groups[category] and (limit is None or len(selected) < limit):
                entry = groups[category].popleft()
                selected.append(entry)
                seen.add(entry["target"])
    return selected


def build_review_queue(root: Path) -> dict[str, Any]:
    candidates = read_json(root / "data" / "candidates.json").get("candidates", [])
    catalog_path = root / "data" / "catalog.json"
    catalog = (
        read_json(catalog_path).get("entries", []) if catalog_path.exists() else []
    )
    entries = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            domain = target_hostname(candidate["target"])
        except (KeyError, TargetError):
            continue
        sources = candidate.get("sources", [])
        existing = next(
            (
                e
                for e in catalog
                if e["target"] == candidate["target"]
                and e["match"] == "exact"
                and e["status"] == "approved"
            ),
            None,
        )
        covering = [e for e in catalog if _is_covered(candidate["target"], [e])]
        entries.append(
            {
                "domain": domain,
                "target": candidate["target"],
                "categories": sorted(set(candidate.get("categories", []))),
                "confidence": candidate.get("confidence"),
                "review_kind": "additional-categories" if covering else "new-target",
                "extend_existing": existing is not None,
                "covered_by": sorted(e["target"] for e in covering),
                "approved_categories": sorted(
                    {c for e in covering for c in e["categories"]}
                ),
                "repository_urls": sorted(
                    {s["repository_url"] for s in sources if s.get("repository_url")}
                )[:5],
                "evidence_urls": list(
                    dict.fromkeys(
                        s["source"]
                        for s in sorted(
                            sources,
                            key=lambda s: (
                                bool(s.get("needs_revalidation")),
                                {"official": 0, "configuration": 1}.get(
                                    s.get("source_role"), 2
                                ),
                                s.get("source", ""),
                            ),
                        )
                        if s.get("source", "").startswith("https://")
                    )
                )[:3],
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
                **evidence_reach(sources),
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
    # Confidence first, then distinct-repository reach, so a bulk vendor pass
    # meets the most widely used endpoints before the long tail.
    entries.sort(
        key=lambda entry: (
            {"high": 0, "medium": 1, "low": 2}.get(entry["confidence"], 3),
            -entry["owner_count"],
            -entry["repository_count"],
            entry["domain"],
        )
    )
    return {
        "schema_version": 1,
        "source": "data/candidates.json",
        "candidate_count": len(entries),
        "entries": entries,
    }


def _text(value: str) -> str:
    return (
        html.escape(value)
        .replace("|", "&#124;")
        .replace("`", "&#96;")
        .replace("\n", " ")
        .replace("\r", " ")
    )


def render_review_queue(document: dict[str, Any]) -> str:
    entries = document["entries"]
    counts = Counter(category for e in entries for category in e["categories"])
    lines = [
        "# Pending package-endpoint review",
        "",
        f"{len(entries)} candidates. Suggestions only; no command below has been executed.",
        "",
        "Confidence describes package evidence, not whether a whole-host block is appropriate. "
        "Check the evidence, public availability, and shared-host impact before promoting. "
        "Observed repository paths are scope clues, not automatically approved path rules.",
        "",
        "## Ecosystem coverage",
        "",
        "| Ecosystem | Pending |",
        "| --- | ---: |",
    ]
    lines.extend(
        f"| {_text(category)} | {count} |" for category, count in sorted(counts.items())
    )
    lines.extend(
        [
            "",
            "## Suggested next batch",
            "",
            "Up to 20 targets, balanced across ecosystems; within each ecosystem, "
            "confidence and distinct-owner reach set the order. Multi-category targets appear once.",
            "",
        ]
    )
    for entry in balanced_entries(entries):
        target = entry["target"]
        flags = ", ".join(entry["review_flags"]) or "none"
        lines.extend(
            [
                f"### {_text(target)}",
                "",
                f"- Ecosystems: {_text(', '.join(entry['categories']))}; evidence confidence: {entry['confidence']}.",
                f"- Review: {entry['review_kind']}; flags: {_text(flags)}.",
                f"- Code reach: {entry['owner_count']} owners / {entry['repository_count']} repositories / {entry['content_count']} content hashes.",
            ]
        )
        if entry["approved_categories"]:
            lines.append(
                f"- Already approved for: {_text(', '.join(entry['approved_categories']))}."
            )
            lines.append(
                f"- Existing coverage: {_text(', '.join(entry['covered_by']))}. A suffix-covered host gets an exact category entry; the suffix is not widened."
            )
        paths = entry["repository_urls"]
        lines.append(
            "- Observed repository targets: "
            + (
                ", ".join(f"`{_text(path)}`" for path in paths)
                if paths
                else "unavailable in older evidence; inspect the configuration before choosing host/path scope."
            )
        )
        for index, url in enumerate(entry["evidence_urls"], 1):
            safe_url = quote(url, safe=":/?=&%#@+~.-_")
            lines.append(f"- [Evidence {index}](<{safe_url}>)")
        categories = " ".join(
            f"--category {shlex.quote(c)}" for c in entry["categories"]
        )
        extend = " --extend" if entry["extend_existing"] else ""
        note = " --review-note 'REPLACE with scope and evidence review'"
        lines.extend(
            [
                "",
                "After inspecting evidence and scope, choose a decision:",
                "",
                "```sh",
                f"python scripts/promote.py {shlex.quote(target)} {categories}{extend}{note}",
                "```",
                "",
                "Or reject:",
                "",
                "```sh",
                f"python scripts/reject.py {shlex.quote(target)} --reason 'REPLACE with rejection rationale'",
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Full queue",
            "",
            "| Target | Ecosystems | Confidence | Owners | Review flags |",
            "| --- | --- | --- | ---: | --- |",
        ]
    )
    for e in entries:
        lines.append(
            f"| {_text(e['target'])} | {_text(', '.join(e['categories']))} | {e['confidence']} | {e['owner_count']} | {_text(', '.join(e['review_flags']))} |"
        )
    return "\n".join(lines) + "\n"


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
    _write_text_atomic(root / QUEUE_MARKDOWN, render_review_queue(document))
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
        f"{domain}\n"
        for domain in sorted({entry["domain"] for entry in expected["entries"]})
    )
    if not text_path.exists():
        problems.append(f"missing generated file: {QUEUE_TEXT.as_posix()}")
    elif text_path.read_text(encoding="utf-8") != expected_domains:
        problems.append(f"stale generated file: {QUEUE_TEXT.as_posix()}")
    markdown_path = root / QUEUE_MARKDOWN
    if not markdown_path.exists():
        problems.append(f"missing generated file: {QUEUE_MARKDOWN.as_posix()}")
    elif markdown_path.read_text(encoding="utf-8") != render_review_queue(expected):
        problems.append(f"stale generated file: {QUEUE_MARKDOWN.as_posix()}")
    return problems

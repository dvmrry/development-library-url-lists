"""Catalog validation and deterministic output rendering."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any

from .normalize import TargetError, normalize_target


class CatalogError(ValueError):
    """Raised when curated data violates the catalog schema."""


def read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CatalogError(f"cannot read {path}: {error}") from error


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    _write_text_atomic(path, content)


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


def load_categories(root: Path) -> list[dict[str, str]]:
    document = read_json(root / "data" / "categories.json")
    if document.get("schema_version") != 1:
        raise CatalogError("unsupported categories schema version")

    categories = document.get("categories")
    if not isinstance(categories, list) or not categories:
        raise CatalogError("categories must be a non-empty list")

    seen_ids: set[str] = set()
    seen_files: set[str] = set()
    validated: list[dict[str, str]] = []
    for category in categories:
        if not isinstance(category, dict):
            raise CatalogError("each category must be an object")
        category_id = category.get("id")
        title = category.get("title")
        filename = category.get("filename")
        if not all(isinstance(value, str) and value for value in (category_id, title, filename)):
            raise CatalogError("category id, title, and filename are required")
        if not category_id.replace("_", "").isalnum() or category_id.lower() != category_id:
            raise CatalogError(f"invalid category id: {category_id!r}")
        if Path(filename).name != filename or not filename.endswith(".txt"):
            raise CatalogError(f"invalid category filename: {filename!r}")
        if category_id in seen_ids or filename in seen_files:
            raise CatalogError(f"duplicate category id or filename: {category_id!r}")
        seen_ids.add(category_id)
        seen_files.add(filename)
        validated.append({"id": category_id, "title": title, "filename": filename})
    return validated


def load_catalog(root: Path) -> dict[str, Any]:
    document = read_json(root / "data" / "catalog.json")
    if document.get("schema_version") != 1:
        raise CatalogError("unsupported catalog schema version")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise CatalogError("catalog entries must be a list")

    category_ids = {item["id"] for item in load_categories(root)}
    allowed_matches = {"exact", "path", "suffix"}
    allowed_statuses = {"approved", "retired"}
    seen: set[tuple[str, str]] = set()
    validated: list[dict[str, Any]] = []

    for position, original in enumerate(entries, start=1):
        if not isinstance(original, dict):
            raise CatalogError(f"entry {position} must be an object")
        entry = deepcopy(original)
        match = entry.get("match")
        if match not in allowed_matches:
            raise CatalogError(f"entry {position} has invalid match mode")
        raw_target = entry.get("target")
        if not isinstance(raw_target, str):
            raise CatalogError(f"entry {position} has no target")
        try:
            target = normalize_target(raw_target, preserve_path=match == "path")
        except TargetError as error:
            raise CatalogError(f"entry {position} target is invalid: {error}") from error
        if match == "suffix" and not target.startswith("."):
            raise CatalogError(f"entry {position} suffix target needs a leading dot")
        if match != "suffix" and target.startswith("."):
            raise CatalogError(f"entry {position} leading-dot target must use suffix match")
        if match == "path" and "/" not in target:
            raise CatalogError(f"entry {position} path match needs a path")

        categories = entry.get("categories")
        if (
            not isinstance(categories, list)
            or not categories
            or not all(isinstance(item, str) for item in categories)
        ):
            raise CatalogError(f"entry {position} categories are invalid")
        unknown = set(categories) - category_ids
        if unknown:
            raise CatalogError(f"entry {position} has unknown categories: {sorted(unknown)}")

        status = entry.get("status")
        if status not in allowed_statuses:
            raise CatalogError(f"entry {position} has invalid status")
        kind = entry.get("kind")
        if not isinstance(kind, str) or not kind:
            raise CatalogError(f"entry {position} has no kind")
        evidence = entry.get("evidence")
        if (
            not isinstance(evidence, list)
            or not evidence
            or not all(
                isinstance(item, str) and item.startswith(("https://", "http://"))
                for item in evidence
            )
        ):
            raise CatalogError(f"entry {position} evidence must contain HTTP(S) URLs")

        identity = (target, match)
        if identity in seen:
            raise CatalogError(f"duplicate catalog entry: {target} ({match})")
        seen.add(identity)

        entry["target"] = target
        entry["categories"] = sorted(set(categories))
        entry["evidence"] = sorted(set(evidence))
        validated.append(entry)

    validated.sort(key=lambda item: (item["target"].lstrip("."), item["match"]))
    return {"schema_version": 1, "entries": validated}


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def build_documents(root: Path) -> dict[str, str]:
    """Build every generated file as a relative-path-to-content mapping."""

    categories = load_categories(root)
    catalog = load_catalog(root)
    approved = [entry for entry in catalog["entries"] if entry["status"] == "approved"]
    documents: dict[str, str] = {}

    for category in categories:
        targets = sorted(
            {
                entry["target"]
                for entry in approved
                if category["id"] in entry["categories"]
            },
            key=lambda value: (value.lstrip("."), value.startswith("."), value),
        )
        documents[category["filename"]] = "".join(f"{target}\n" for target in targets)

    all_targets = sorted(
        {entry["target"] for entry in approved},
        key=lambda value: (value.lstrip("."), value.startswith("."), value),
    )
    documents["all.txt"] = "".join(f"{target}\n" for target in all_targets)
    documents["catalog.json"] = (
        json.dumps(catalog, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )

    manifest_files = {
        name: {
            "sha256": _sha256(content),
            "target_count": len([line for line in content.splitlines() if line])
            if name.endswith(".txt")
            else None,
        }
        for name, content in sorted(documents.items())
    }
    manifest = {
        "schema_version": 1,
        "source": "data/catalog.json",
        "approved_entry_count": len(approved),
        "unique_target_count": len(all_targets),
        "files": manifest_files,
    }
    documents["manifest.json"] = (
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )
    documents["SHA256SUMS"] = "".join(
        f"{_sha256(content)}  {name}\n"
        for name, content in sorted(documents.items())
    )
    return documents


def write_documents(root: Path) -> None:
    dist = root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    for relative_name, content in build_documents(root).items():
        _write_text_atomic(dist / relative_name, content)


def validate_documents(root: Path) -> list[str]:
    """Return human-readable differences between expected and on-disk output."""

    expected = build_documents(root)
    dist = root / "dist"
    problems: list[str] = []
    for relative_name, content in expected.items():
        path = dist / relative_name
        if not path.exists():
            problems.append(f"missing generated file: dist/{relative_name}")
        elif path.read_text(encoding="utf-8") != content:
            problems.append(f"stale generated file: dist/{relative_name}")

    expected_names = set(expected)
    if dist.exists():
        for path in sorted(item for item in dist.iterdir() if item.is_file()):
            if path.name not in expected_names:
                problems.append(f"unexpected generated file: dist/{path.name}")
    return problems

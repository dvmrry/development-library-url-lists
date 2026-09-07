"""Refresh every public artifact affected by a local review decision."""

from pathlib import Path

from .catalog import write_documents
from .review_queue import write_review_queue


def refresh_outputs(root: Path) -> None:
    write_documents(root)
    write_review_queue(root)

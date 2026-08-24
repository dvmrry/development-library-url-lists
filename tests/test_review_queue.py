from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import write_json_atomic
from url_lists.review_queue import (
    QUEUE_TEXT,
    build_review_queue,
    validate_review_queue,
    write_review_queue,
)


class ReviewQueueTests(unittest.TestCase):
    def test_exports_only_review_metadata_in_confidence_order(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json_atomic(
                root / "data" / "candidates.json",
                {
                    "schema_version": 1,
                    "candidates": [
                        self.candidate("low.vendor.net", "low"),
                        self.candidate("high.vendor.net", "high"),
                    ],
                },
            )
            queue = build_review_queue(root)
            self.assertEqual(queue["candidate_count"], 2)
            self.assertEqual(queue["entries"][0]["domain"], "high.vendor.net")
            self.assertNotIn("sources", queue["entries"][0])
            self.assertEqual(queue["entries"][0]["source_kinds"], ["published-list"])
            self.assertEqual(queue["entries"][0]["source_ecosystems"], ["archlinux"])

    def test_generated_queue_and_plain_domain_list_validate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json_atomic(
                root / "data" / "candidates.json",
                {
                    "schema_version": 1,
                    "candidates": [self.candidate("mirror.vendor.net", "high")],
                },
            )
            write_review_queue(root)
            self.assertEqual(validate_review_queue(root), [])
            self.assertEqual(
                (root / QUEUE_TEXT).read_text(),
                "mirror.vendor.net\n",
            )

    @staticmethod
    def candidate(target: str, confidence: str) -> dict[str, object]:
        return {
            "target": target,
            "categories": ["os_packages"],
            "confidence": confidence,
            "review_flags": [],
            "sources": [
                {
                    "source_kind": "published-list",
                    "source_ecosystem": "archlinux",
                    "source_role": "official",
                }
            ],
        }


if __name__ == "__main__":
    unittest.main()

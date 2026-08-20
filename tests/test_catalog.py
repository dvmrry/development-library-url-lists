from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import (
    CatalogError,
    build_documents,
    validate_documents,
    write_documents,
)


class CatalogTests(unittest.TestCase):
    def make_root(self, catalog_entries: list[dict]) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        data = root / "data"
        data.mkdir()
        (data / "categories.json").write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "categories": [
                        {"id": "python", "title": "Python", "filename": "python.txt"},
                        {"id": "jvm", "title": "JVM", "filename": "jvm.txt"},
                    ],
                }
            ),
            encoding="utf-8",
        )
        (data / "catalog.json").write_text(
            json.dumps({"schema_version": 1, "entries": catalog_entries}),
            encoding="utf-8",
        )
        return root

    def test_renders_approved_entries_deterministically(self) -> None:
        root = self.make_root(
            [
                {
                    "target": "z.example.org",
                    "match": "exact",
                    "categories": ["python"],
                    "kind": "mirror",
                    "status": "approved",
                    "evidence": ["https://evidence.example.org/z"],
                },
                {
                    "target": ".packages.example.net",
                    "match": "suffix",
                    "categories": ["jvm", "python"],
                    "kind": "provider",
                    "status": "approved",
                    "evidence": ["https://evidence.example.org/provider"],
                },
                {
                    "target": "retired.example.com",
                    "match": "exact",
                    "categories": ["python"],
                    "kind": "mirror",
                    "status": "retired",
                    "evidence": ["https://evidence.example.org/retired"],
                },
            ]
        )
        documents = build_documents(root)
        self.assertEqual(
            documents["python.txt"],
            ".packages.example.net\nz.example.org\n",
        )
        self.assertEqual(documents["jvm.txt"], ".packages.example.net\n")
        self.assertNotIn("retired.example.com", documents["all.txt"])
        self.assertIn("SHA256SUMS", documents)
        self.assertIn("manifest.json", documents)

        write_documents(root)
        self.assertEqual(validate_documents(root), [])

    def test_rejects_duplicate_targets(self) -> None:
        entry = {
            "target": "repo.example.org",
            "match": "exact",
            "categories": ["python"],
            "kind": "mirror",
            "status": "approved",
            "evidence": ["https://evidence.example.org/"],
        }
        root = self.make_root([entry, dict(entry)])
        with self.assertRaises(CatalogError):
            build_documents(root)


if __name__ == "__main__":
    unittest.main()

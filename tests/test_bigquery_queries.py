"""Offline query-contract checks, not a substitute for a BigQuery dry run."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.seed_import import map_path_to_extractor


class BigQueryQueryTests(unittest.TestCase):
    def query(self, tier: str) -> str:
        return (ROOT / "queries" / "bigquery" / f"{tier}-select.sql").read_text()

    def test_selects_preserve_import_contract_and_sample_only(self):
        for tier in ("tier-a", "tier-b"):
            with self.subTest(tier=tier):
                sql = self.query(tier)
                self.assertIn("f.repo_name AS repo_name", sql)
                self.assertIn("f.path AS path", sql)
                self.assertIn("c.content AS content", sql)
                self.assertIn("ON f.id = c.id", sql)
                self.assertIn("AND c.binary IS NOT TRUE", sql)
                self.assertEqual(
                    re.findall(r"`([^`]+)`", sql),
                    [
                        "bigquery-public-data.github_repos.files",
                        "bigquery-public-data.github_repos.sample_contents",
                    ],
                )
                statements = re.sub(r"--[^\n]*", "", sql)
                self.assertTrue(statements.lstrip().startswith("SELECT"))
                self.assertNotRegex(statements.upper(), r"\b(EXPORT|CREATE|LIMIT)\b")

    def test_filename_patterns_match_supported_paths_only(self):
        paths = {
            "tier-a": [
                ".npmrc", ".yarnrc", ".yarnrc.yml", "pip.conf", "pip.ini",
                ".condarc", "environment.yml", "environment.yaml", "settings.xml",
                "NuGet.Config", "paket.dependencies", "Pipfile", "bunfig.toml",
            ],
            "tier-b": [
                "package.json", "pom.xml", "requirements.txt", "requirements-dev.txt",
                "pyproject.toml", "build.gradle", "build.gradle.kts", "app.csproj",
                "Directory.Packages.props",
            ],
        }
        for tier, names in paths.items():
            pattern = re.search(r"r'([^']+)'", self.query(tier)).group(1)
            for name in names:
                for path in (name, f"nested/{name}", f"nested/{name.upper()}"):
                    with self.subTest(tier=tier, path=path):
                        self.assertRegex(path, pattern)
                        self.assertIsNotNone(map_path_to_extractor(path))
                        self.assertNotRegex(f"{path}.bak", pattern)
            for path in ("README.md", "prefix.npmrc", "xpip.conf", "requirements/a.txt"):
                with self.subTest(tier=tier, excluded=path):
                    self.assertNotRegex(path, pattern)


if __name__ == "__main__":
    unittest.main()

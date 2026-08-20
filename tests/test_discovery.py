from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.discovery import (
    _trusted_ascii_url,
    extract_context_urls,
    filter_observations,
    merge_candidates,
)


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.exclusions = {
            "exact_hosts": ["github.com", "localhost"],
            "suffixes": [".internal", ".test"],
            "shared_hosts": ["amazonaws.com"],
        }
        self.catalog = [
            {
                "target": "registry.npmjs.org",
                "match": "exact",
                "status": "approved",
            },
            {
                "target": ".jfrog.io",
                "match": "suffix",
                "status": "approved",
            },
        ]

    def test_filters_known_private_and_shared_hosts(self) -> None:
        observations = [
            self.observation("https://registry.npmjs.org/"),
            self.observation("https://tenant.jfrog.io/artifactory/npm"),
            self.observation("https://bucket.amazonaws.com/packages"),
            self.observation("http://repo.internal/simple"),
            self.observation("https://oddball.example.org/simple"),
        ]
        filtered = filter_observations(
            observations,
            exclusions=self.exclusions,
            catalog_entries=self.catalog,
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["target"], "oddball.example.org")
        self.assertNotIn("discovered_url", filtered[0])

    def test_merge_is_stable_without_new_evidence(self) -> None:
        observation = {
            "target": "oddball.example.org",
            "category": "python",
            "source": "https://github.com/acme/project/blob/main/pip.conf",
            "source_kind": "github-code",
            "repository": "acme/project",
        }
        empty = {"schema_version": 1, "candidates": []}
        first, additions = merge_candidates(empty, [observation], today="2026-08-20")
        self.assertEqual(additions, 1)
        second, additions = merge_candidates(first, [observation], today="2026-08-21")
        self.assertEqual(additions, 0)
        self.assertEqual(first, second)

    def test_context_extraction_ignores_unrelated_project_urls(self) -> None:
        content = """
homepage = "https://project.example.com"
index-url = https://packages.example.org/simple
documentation = "https://docs.example.com"
"""
        self.assertEqual(
            extract_context_urls(content, ["index-url"]),
            ["https://packages.example.org/simple"],
        )

    def test_trusted_api_path_is_ascii_encoded(self) -> None:
        encoded = _trusted_ascii_url(
            "https://api.github.com/repos/acme/project/contents/\u200efile"
        )
        self.assertEqual(
            encoded,
            "https://api.github.com/repos/acme/project/contents/%E2%80%8Efile",
        )

    def test_confidence_increases_with_independent_repositories(self) -> None:
        observations = []
        for repository in ("one/project", "two/project"):
            observation = self.observation("https://mirror.example.org/simple")
            observation["target"] = "mirror.example.org"
            del observation["discovered_url"]
            observation["repository"] = repository
            observations.append(observation)
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            observations,
            today="2026-08-20",
        )
        self.assertEqual(merged["candidates"][0]["confidence"], "medium")

    @staticmethod
    def observation(url: str) -> dict[str, str]:
        return {
            "category": "python",
            "discovered_url": url,
            "source": "https://github.com/acme/project/blob/main/pip.conf",
            "source_kind": "github-code",
            "repository": "acme/project",
        }


if __name__ == "__main__":
    unittest.main()

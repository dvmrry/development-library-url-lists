from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.published_sources import (
    PublishedSourceError,
    _safe_source_url,
    parse_cran_mirrors,
    parse_ecosystems_registries,
    parse_mirrorz_scoring,
)


class PublishedSourceTests(unittest.TestCase):
    def test_ecosystems_maps_known_types_and_actual_api_endpoint(self) -> None:
        observations = parse_ecosystems_registries(
            [
                {
                    "url": "https://hub.docker.com",
                    "ecosystem": "docker",
                    "purl_type": "docker",
                    "metadata": {"api_url": "https://registry-1.docker.io"},
                },
                {
                    "url": "https://packages.unknown.invalid",
                    "ecosystem": "unknown",
                    "purl_type": "unknown",
                },
            ],
            source_url=(
                "https://packages.ecosyste.ms/api/v1/registries?page=1&per_page=100"
            ),
        )
        self.assertEqual(
            [item["discovered_url"] for item in observations],
            ["https://hub.docker.com", "https://registry-1.docker.io"],
        )
        self.assertTrue(all(item["category"] == "containers" for item in observations))
        self.assertTrue(
            all(item["source_role"] == "registry-catalog" for item in observations)
        )

    def test_record_fingerprint_ignores_unrelated_volatile_metadata(self) -> None:
        base = {
            "url": "https://packages.vendor.net",
            "ecosystem": "npm",
            "purl_type": "npm",
            "packages_count": 10,
        }
        changed = dict(base, packages_count=999999, updated_at="later")
        first = parse_ecosystems_registries(
            [base],
            source_url=(
                "https://packages.ecosyste.ms/api/v1/registries?page=1&per_page=100"
            ),
        )
        second = parse_ecosystems_registries(
            [changed],
            source_url=(
                "https://packages.ecosyste.ms/api/v1/registries?page=1&per_page=100"
            ),
        )
        self.assertEqual(
            first[0]["content_sha256"],
            second[0]["content_sha256"],
        )

    def test_mirrorz_deduplicates_repeated_resolvers(self) -> None:
        observations = parse_mirrorz_scoring(
            {
                "scores": [
                    {"resolve": "mirrors.example.edu"},
                    {"resolve": "mirrors.example.edu"},
                    {"resolve": "mirror.other.edu"},
                ]
            },
        )
        self.assertEqual(
            [item["discovered_url"] for item in observations],
            ["https://mirror.other.edu", "https://mirrors.example.edu"],
        )
        self.assertTrue(all(item["category"] == "multi_ecosystem" for item in observations))

    def test_cran_requires_official_ok_flag(self) -> None:
        text = (
            '"Name","URL","OK"\n'
            '"Healthy","https://cran.example.edu/CRAN/",1\n'
            '"Disabled","https://old.example.edu/CRAN/",0\n'
        )
        observations = parse_cran_mirrors(text)
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["discovered_url"], "https://cran.example.edu/CRAN/")
        self.assertEqual(observations[0]["source_role"], "official")

    def test_published_source_network_allowlist_is_exact(self) -> None:
        self.assertEqual(
            _safe_source_url("https://cran.r-project.org/CRAN_mirrors.csv"),
            "https://cran.r-project.org/CRAN_mirrors.csv",
        )
        with self.assertRaises(PublishedSourceError):
            _safe_source_url("https://attacker.example/mirrors.json")


if __name__ == "__main__":
    unittest.main()

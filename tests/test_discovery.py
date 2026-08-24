from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.discovery import (
    _reconcile_current_candidates,
    _source_role,
    _trusted_ascii_url,
    collect_github_code,
    filter_observations,
    merge_candidates,
    reconcile_published_snapshot,
)


class DiscoveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.exclusions = {
            "exact_hosts": ["github.com", "localhost"],
            "suffixes": [".artipie", ".internal", ".test"],
            "shared_hosts": ["amazonaws.com", "mvnrepository.com"],
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
            self.observation("https://artipie.artipie:9300/packages"),
            self.observation("https://mvnrepository.com/artifact/example"),
            self.observation("http://repo.internal/simple"),
            self.observation("https://oddball.acme.org/simple"),
        ]
        filtered = filter_observations(
            observations,
            exclusions=self.exclusions,
            catalog_entries=self.catalog,
        )
        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0]["target"], "oddball.acme.org")
        self.assertNotIn("discovered_url", filtered[0])

    def test_merge_is_stable_without_new_evidence(self) -> None:
        observation = {
            "target": "oddball.acme.org",
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

    def test_rejected_target_stays_filtered(self) -> None:
        filtered = filter_observations(
            [self.observation("https://noise.example.org/packages")],
            exclusions=self.exclusions,
            catalog_entries=self.catalog,
            rejected_targets={"noise.example.org"},
        )
        self.assertEqual(filtered, [])

    def test_legacy_candidate_gets_review_metadata(self) -> None:
        legacy = {
            "schema_version": 1,
            "candidates": [
                {
                    "target": "docs.example.org",
                    "match": "exact",
                    "categories": ["python"],
                    "confidence": "low",
                    "first_seen": "2026-08-20",
                    "last_evidence_change": "2026-08-20",
                    "sources": [
                        {
                            "source": "https://github.com/acme/project/blob/main/pip.conf",
                            "source_kind": "github-code",
                            "repository": "acme/project",
                        }
                    ],
                }
            ],
        }
        merged, additions = merge_candidates(legacy, [], today="2026-08-21")
        self.assertEqual(additions, 0)
        self.assertEqual(
            merged["candidates"][0]["review_flags"],
            ["documentation-like", "placeholder-like"],
        )

    def test_hard_rejects_documentation_and_placeholder_targets(self) -> None:
        filtered = filter_observations(
            [
                self.observation("https://docs.vendor.net/packages"),
                self.observation("https://hackage.example.com/packages"),
                self.observation("https://en.wikipedia.org/wiki/Haskell"),
                self.observation("https://nexus3.xxx.com/simple"),
                self.observation("https://youappname.herokuapp.com/packages"),
                self.observation("https://packages.vendor.net/simple"),
            ],
            exclusions=self.exclusions,
            catalog_entries=self.catalog,
        )
        self.assertEqual(
            [item["target"] for item in filtered],
            ["packages.vendor.net"],
        )

    def test_trusted_api_path_is_ascii_encoded(self) -> None:
        encoded = _trusted_ascii_url(
            "https://api.github.com/repos/acme/project/contents/\u200efile"
        )
        self.assertEqual(
            encoded,
            "https://api.github.com/repos/acme/project/contents/%E2%80%8Efile",
        )

    def test_github_collection_records_precise_extractor_provenance(self) -> None:
        content = (
            'homepage = "https://project.vendor.net"\n'
            "index-url = https://packages.vendor.net/simple\n"
        )
        search_result = {
            "items": [
                {
                    "url": "https://api.github.com/repos/acme/project/contents/pip.conf",
                    "html_url": (
                        "https://github.com/acme/project/blob/"
                        "0123456789012345678901234567890123456789/pip.conf"
                    ),
                    "path": "config/pip.conf",
                    "repository": {"full_name": "acme/project"},
                }
            ]
        }
        content_result = {
            "encoding": "base64",
            "content": base64.b64encode(content.encode()).decode(),
        }
        with patch(
            "url_lists.discovery._get_json",
            side_effect=[search_result, content_result],
        ):
            observations = collect_github_code(
                [
                    {
                        "id": "pip-index",
                        "ecosystem": "python",
                        "query": '"index-url" filename:pip.conf',
                        "extractor": "pip-config",
                        "max_results": 20,
                    }
                ],
                token="test-token",
                delay_seconds=0,
            )
        self.assertEqual(len(observations), 1)
        observation = observations[0]
        self.assertEqual(
            observation["discovered_url"],
            "https://packages.vendor.net/simple",
        )
        self.assertEqual(observation["query_id"], "pip-index")
        self.assertEqual(observation["extractor"], "pip-config")
        self.assertEqual(observation["source_role"], "configuration")
        self.assertEqual(
            observation["content_sha256"],
            hashlib.sha256(content.encode()).hexdigest(),
        )

    def test_extraction_failure_skips_the_file_without_aborting_the_run(self) -> None:
        search_result = {
            "items": [
                {
                    "url": "https://api.github.com/repos/acme/broken/contents/x",
                    "html_url": "https://github.com/acme/broken/blob/a/x",
                    "path": "x",
                    "repository": {"full_name": "acme/broken"},
                },
                {
                    "url": "https://api.github.com/repos/acme/good/contents/pip.conf",
                    "html_url": "https://github.com/acme/good/blob/b/pip.conf",
                    "path": "pip.conf",
                    "repository": {"full_name": "acme/good"},
                },
            ]
        }
        good_content = {
            "encoding": "base64",
            "content": base64.b64encode(
                b"index-url = https://packages.vendor.net/simple\n"
            ).decode(),
        }
        broken_content = {
            "encoding": "base64",
            "content": base64.b64encode(b"whatever\n").decode(),
        }
        stderr = io.StringIO()
        with patch(
            "url_lists.discovery._get_json",
            side_effect=[search_result, broken_content, good_content],
        ), patch(
            "url_lists.discovery.extract_registry_urls",
            side_effect=[
                RuntimeError("degenerate input"),
                ["https://packages.vendor.net/simple"],
            ],
        ), contextlib.redirect_stderr(stderr):
            observations = collect_github_code(
                [
                    {
                        "id": "pip-index",
                        "ecosystem": "python",
                        "query": '"index-url" filename:pip.conf',
                        "extractor": "pip-config",
                        "max_results": 20,
                    }
                ],
                token="test-token",
                delay_seconds=0,
            )
        self.assertEqual(len(observations), 1)
        self.assertEqual(observations[0]["repository"], "acme/good")
        report = stderr.getvalue()
        self.assertIn("Extraction failed and was skipped", report)
        self.assertIn("repository=acme/broken", report)
        self.assertIn("skipped 1 file(s)", report)

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

    def test_review_flags_are_deterministic(self) -> None:
        observation = self.observation("https://docs.yourcompany.com/packages")
        observation["target"] = "docs.yourcompany.com"
        del observation["discovered_url"]
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation],
            today="2026-08-20",
        )
        self.assertEqual(
            merged["candidates"][0]["review_flags"],
            ["documentation-like", "placeholder-like"],
        )

    def test_documentation_only_evidence_never_increases_confidence(self) -> None:
        observations = []
        for repository in ("one/project", "two/project", "three/project"):
            observation = self.observation("https://mirror.vendor.net/simple")
            observation["target"] = "mirror.vendor.net"
            del observation["discovered_url"]
            observation["repository"] = repository
            observation["source_role"] = "documentation"
            observations.append(observation)
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            observations,
            today="2026-08-20",
        )
        candidate = merged["candidates"][0]
        self.assertEqual(candidate["confidence"], "low")
        self.assertEqual(
            candidate["review_flags"],
            ["non-configuration-evidence-only"],
        )

    def test_copied_configuration_does_not_inflate_confidence(self) -> None:
        observations = []
        for repository in ("one/project", "two/project", "three/project"):
            observation = self.observation("https://mirror.vendor.net/simple")
            observation["target"] = "mirror.vendor.net"
            del observation["discovered_url"]
            observation["repository"] = repository
            observation["source_role"] = "configuration"
            observation["content_sha256"] = "a" * 64
            observations.append(observation)
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            observations,
            today="2026-08-20",
        )
        self.assertEqual(merged["candidates"][0]["confidence"], "low")

    def test_retired_service_is_flagged_and_capped_low(self) -> None:
        observations = []
        for repository in ("one/project", "two/project", "three/project"):
            observation = self.observation("https://dl.bintray.com/acme/packages")
            observation["target"] = "dl.bintray.com"
            del observation["discovered_url"]
            observation["repository"] = repository
            observations.append(observation)
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            observations,
            today="2026-08-20",
        )
        candidate = merged["candidates"][0]
        self.assertEqual(candidate["confidence"], "low")
        self.assertEqual(candidate["review_flags"], ["retired-service"])

    def test_official_purl_definition_is_high_confidence(self) -> None:
        observation = self.observation("https://packages.vendor.net/simple")
        observation["target"] = "packages.vendor.net"
        del observation["discovered_url"]
        observation["source_kind"] = "purl-definition"
        observation["source_role"] = "official"
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation],
            today="2026-08-20",
        )
        self.assertEqual(merged["candidates"][0]["confidence"], "high")

    def test_official_mirror_list_is_high_confidence(self) -> None:
        observation = self.observation("https://mirror.vendor.net/packages")
        observation["target"] = "mirror.vendor.net"
        del observation["discovered_url"]
        observation["source_kind"] = "published-list"
        observation["source_role"] = "official"
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation],
            today="2026-08-20",
        )
        self.assertEqual(merged["candidates"][0]["confidence"], "high")

    def test_third_party_registry_catalog_is_medium_confidence(self) -> None:
        observation = self.observation("https://packages.vendor.net/simple")
        observation["target"] = "packages.vendor.net"
        del observation["discovered_url"]
        observation["source_kind"] = "published-list"
        observation["source_role"] = "registry-catalog"
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation],
            today="2026-08-20",
        )
        self.assertEqual(merged["candidates"][0]["confidence"], "medium")

    def test_successful_published_refresh_removes_absent_mirror(self) -> None:
        observation = self.observation("https://removed.vendor.net/packages")
        observation["target"] = "removed.vendor.net"
        del observation["discovered_url"]
        observation.update(
            {
                "source_kind": "published-list",
                "source_role": "official",
                "query_id": "official-mirrors",
                "source_path": "https://removed.vendor.net/packages",
            }
        )
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation],
            today="2026-08-20",
        )
        reconciled = reconcile_published_snapshot(
            merged,
            [],
            successful_query_ids={"official-mirrors"},
            today="2026-08-21",
        )
        self.assertEqual(reconciled["candidates"], [])

    def test_failed_published_refresh_preserves_prior_mirror(self) -> None:
        observation = self.observation("https://retained.vendor.net/packages")
        observation["target"] = "retained.vendor.net"
        del observation["discovered_url"]
        observation.update(
            {
                "source_kind": "published-list",
                "source_role": "official",
                "query_id": "failed-mirrors",
                "source_path": "https://retained.vendor.net/packages",
            }
        )
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation],
            today="2026-08-20",
        )
        reconciled = reconcile_published_snapshot(
            merged,
            [],
            successful_query_ids={"different-source"},
            today="2026-08-21",
        )
        self.assertEqual(len(reconciled["candidates"]), 1)

    def test_removing_published_source_recomputes_mixed_candidate_category(self) -> None:
        github = self.observation("https://mixed.vendor.net/simple")
        github["target"] = "mixed.vendor.net"
        del github["discovered_url"]
        published = dict(github)
        published.update(
            {
                "category": "multi_ecosystem",
                "source": "https://catalog.vendor.net/mirrors.json",
                "source_kind": "published-list",
                "source_role": "mirror-catalog",
                "repository": "vendor/mirror-catalog",
                "query_id": "mirror-catalog",
                "source_path": "https://mixed.vendor.net/packages",
            }
        )
        merged, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [github, published],
            today="2026-08-20",
        )
        reconciled = reconcile_published_snapshot(
            merged,
            [],
            successful_query_ids={"mirror-catalog"},
            today="2026-08-21",
        )
        candidate = reconciled["candidates"][0]
        self.assertEqual(candidate["categories"], ["python"])
        self.assertEqual(len(candidate["sources"]), 1)

    def test_merge_preserves_extractor_provenance(self) -> None:
        observation = self.observation("https://packages.vendor.net/simple")
        observation["target"] = "packages.vendor.net"
        del observation["discovered_url"]
        observation.update(
            {
                "content_sha256": "a" * 64,
                "extractor": "pip-config",
                "query_id": "pip-index",
                "source_path": "pip.conf",
                "source_role": "configuration",
            }
        )
        merged, additions = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation],
            today="2026-08-20",
        )
        self.assertEqual(additions, 1)
        source = merged["candidates"][0]["sources"][0]
        self.assertEqual(source["extractor"], "pip-config")
        self.assertEqual(source["query_id"], "pip-index")
        self.assertEqual(source["content_sha256"], "a" * 64)

    def test_new_commit_updates_the_same_source_path_without_duplication(self) -> None:
        observation = self.observation("https://packages.vendor.net/simple")
        observation["target"] = "packages.vendor.net"
        del observation["discovered_url"]
        observation.update(
            {
                "content_sha256": "a" * 64,
                "extractor": "pip-config",
                "query_id": "pip-index",
                "source_path": "pip.conf",
                "source_role": "configuration",
            }
        )
        first, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation],
            today="2026-08-20",
        )
        observation["source"] = (
            "https://github.com/acme/project/blob/new-commit/pip.conf"
        )
        observation["content_sha256"] = "b" * 64
        second, additions = merge_candidates(
            first,
            [observation],
            today="2026-08-21",
        )
        sources = second["candidates"][0]["sources"]
        self.assertEqual(additions, 0)
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["content_sha256"], "b" * 64)
        self.assertIn("new-commit", sources[0]["source"])

    def test_changed_rules_discard_the_stale_candidate_snapshot(self) -> None:
        current = {
            "schema_version": 1,
            "discovery_rules_sha256": "a" * 64,
            "candidates": [{"target": "noise.vendor.net"}],
        }
        reconciled = _reconcile_current_candidates(
            current,
            rules_sha256="b" * 64,
            exclusions=self.exclusions,
            catalog_entries=self.catalog,
            rejected_targets=set(),
        )
        self.assertEqual(reconciled["candidates"], [])
        self.assertEqual(reconciled["discovery_rules_sha256"], "b" * 64)

    def test_source_roles_distinguish_docs_tests_examples_and_config(self) -> None:
        self.assertEqual(_source_role("docs/setup/pip.conf"), "documentation")
        self.assertEqual(_source_role("tests/fixtures/pip.conf"), "test")
        self.assertEqual(_source_role("examples/pip.conf"), "example")
        self.assertEqual(_source_role("config/pip.conf"), "configuration")

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

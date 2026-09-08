from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import read_json, write_json_atomic, validate_documents
from url_lists.discovery import (
    DiscoveryError,
    _get_bytes,
    _RetryBudget,
    _retry_delay,
    _reconcile_current_candidates,
    filter_observations,
    merge_candidates,
    merge_candidate_snapshots,
    run_network_discovery,
)
from url_lists.outputs import refresh_outputs
from url_lists.review_queue import (
    balanced_entries,
    build_review_queue,
    validate_review_queue,
    QUEUE_MARKDOWN,
)
from url_lists.published_sources import PublishedCollection, PublishedSourceError
from url_lists.traffic_review import review_traffic
from url_lists.llm_review import create_review_report, write_review_report


def script(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def observation(
    target="packages.vendor.net", category="python", kind="bigquery-github"
):
    return {
        "target": target,
        "category": category,
        "source_kind": kind,
        "source": "https://github.com/acme/project/blob/HEAD/pip.conf",
        "source_path": "pip.conf",
        "source_role": "configuration",
        "repository": "acme/project",
        "content_sha256": "a" * 64,
    }


class ReviewWorkflowTests(unittest.TestCase):
    def make_root(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        for name in ("data", "src"):
            shutil.copytree(
                ROOT / name, root / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        candidate, _ = merge_candidates(
            {"schema_version": 1, "candidates": []}, [observation()]
        )
        write_json_atomic(root / "data/candidates.json", candidate)
        refresh_outputs(root)
        return root

    def call_script(self, name, root, *args):
        module = script(name)
        with (
            patch.object(module, "ROOT", root),
            patch.object(sys, "argv", [name, *args]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            return module.main()

    def test_decisions_refresh_all_outputs(self):
        for name, args in (
            ("promote", []),
            ("reject", ["--reason", "not a public registry"]),
        ):
            with self.subTest(name=name):
                root = self.make_root()
                self.assertEqual(
                    self.call_script(name, root, "packages.vendor.net", *args), 0
                )
                self.assertEqual(validate_review_queue(root), [])
                self.assertEqual(validate_documents(root), [])
                self.assertEqual(
                    read_json(root / "data/candidates.json")["candidates"], []
                )

    def test_category_extension_is_explicit_and_preserves_other_categories(self):
        root = self.make_root()
        self.call_script("promote", root, "packages.vendor.net")
        doc, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation(category="javascript"), observation(category="jvm")],
        )
        write_json_atomic(root / "data/candidates.json", doc)
        refresh_outputs(root)
        entry = build_review_queue(root)["entries"][0]
        self.assertEqual(entry["review_kind"], "additional-categories")
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.call_script(
                "promote", root, "packages.vendor.net", "--category", "javascript"
            )
        self.call_script(
            "promote",
            root,
            "packages.vendor.net",
            "--category",
            "javascript",
            "--extend",
        )
        catalog = read_json(root / "data/catalog.json")
        approved = next(
            e for e in catalog["entries"] if e["target"] == "packages.vendor.net"
        )
        self.assertEqual(approved["categories"], ["javascript", "python"])
        self.assertEqual(
            read_json(root / "data/candidates.json")["candidates"][0]["categories"],
            ["jvm"],
        )
        self.assertEqual(validate_review_queue(root), [])

    def test_rule_changes_retain_seed_evidence_until_refreshed(self):
        root = self.make_root()
        current = read_json(root / "data/candidates.json")
        changed = _reconcile_current_candidates(
            current,
            rules_sha256="b" * 64,
            exclusions={},
            catalog_entries=[],
            rejected_targets=[],
        )
        candidate = changed["candidates"][0]
        self.assertIn("evidence-needs-revalidation", candidate["review_flags"])
        self.assertTrue(candidate["sources"][0]["needs_revalidation"])
        self.assertNotIn("needs_revalidation", current["candidates"][0]["sources"][0])
        write_json_atomic(root / "data/candidates.json", changed)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.call_script("promote", root, "packages.vendor.net")
        refreshed, _ = merge_candidates(changed, [observation()])
        self.assertNotIn(
            "evidence-needs-revalidation", refreshed["candidates"][0]["review_flags"]
        )
        self.call_script(
            "promote",
            root,
            "packages.vendor.net",
            "--review-note",
            "Confirmed public index and dedicated host",
        )
        self.assertEqual(validate_review_queue(root), [])

    def test_category_discovery_preserves_paths_without_publishing(self):
        catalog = [
            {
                "target": "packages.vendor.net",
                "status": "approved",
                "match": "exact",
                "categories": ["python"],
            }
        ]
        obs = {
            **observation(category="javascript"),
            "discovered_url": "https://packages.vendor.net/npm/",
        }
        filtered = filter_observations([obs], exclusions={}, catalog_entries=catalog)
        self.assertEqual(filtered[0]["repository_url"], "packages.vendor.net/npm")
        self.assertEqual(catalog[0]["categories"], ["python"])
        obs["category"] = "python"
        self.assertEqual(
            filter_observations([obs], exclusions={}, catalog_entries=catalog), []
        )

    def test_restoring_automation_does_not_replace_offline_seed(self):
        current, _ = merge_candidates(
            {"schema_version": 1, "candidates": []}, [observation()]
        )
        old, _ = merge_candidates(
            {"schema_version": 1, "candidates": []},
            [observation("other.vendor.net", kind="github-code")],
        )
        current["discovery_rules_sha256"] = "a" * 64
        old["discovery_rules_sha256"] = "b" * 64
        combined = merge_candidate_snapshots(current, old)
        self.assertEqual(
            {c["target"] for c in combined["candidates"]},
            {"packages.vendor.net", "other.vendor.net"},
        )
        self.assertTrue(combined["candidates"][0]["sources"][0]["needs_revalidation"])
        self.assertEqual(merge_candidate_snapshots(combined, old), combined)

    def test_review_batch_balances_ecosystems_and_validates_markdown(self):
        root = self.make_root()
        obs = [observation(f"r{i}.vendor.net", category="r") for i in range(30)]
        obs += [
            observation("python.vendor.net"),
            observation("java.vendor.net", category="jvm"),
        ]
        doc, _ = merge_candidates({"schema_version": 1, "candidates": []}, obs)
        write_json_atomic(root / "data/candidates.json", doc)
        refresh_outputs(root)
        batch = balanced_entries(build_review_queue(root)["entries"], 3)
        self.assertEqual({e["categories"][0] for e in batch}, {"r", "python", "jvm"})
        self.assertEqual(validate_review_queue(root), [])
        (root / QUEUE_MARKDOWN).write_text("stale")
        self.assertIn(
            f"stale generated file: {QUEUE_MARKDOWN}", validate_review_queue(root)
        )

    def test_purl_survives_total_github_outage(self):
        root = self.make_root()
        metrics = {}
        obs = {
            **observation("purl.vendor.net"),
            "discovered_url": "https://purl.vendor.net/",
        }
        with (
            patch(
                "url_lists.discovery.collect_github_code",
                side_effect=DiscoveryError("throttled"),
            ),
            patch("url_lists.discovery.collect_purl_definitions", return_value=[obs]),
            patch(
                "url_lists.discovery.collect_published_sources",
                side_effect=PublishedSourceError("offline"),
            ),
            contextlib.redirect_stderr(io.StringIO()),
        ):
            run_network_discovery(root, token="test", metrics=metrics)
        self.assertEqual(metrics["status"], "partial")
        self.assertIn("package-url", metrics["refreshed_sources"])
        self.assertEqual(metrics["candidates_added"], 1)

    def test_reconciliation_only_changes_are_persisted(self):
        root = self.make_root()
        doc = read_json(root / "data/candidates.json")
        doc["candidates"][0]["target"] = "registry.npmjs.org"
        doc["candidates"][0]["categories"] = ["javascript"]
        write_json_atomic(root / "data/candidates.json", doc)
        with (
            patch("url_lists.discovery.collect_github_code", return_value=[]),
            patch("url_lists.discovery.collect_purl_definitions", return_value=[]),
            patch(
                "url_lists.discovery.collect_published_sources",
                return_value=PublishedCollection([], frozenset(), frozenset()),
            ),
        ):
            run_network_discovery(root, token="test")
        self.assertEqual(read_json(root / "data/candidates.json")["candidates"], [])

    def test_total_source_outage_preserves_snapshot(self):
        root = self.make_root()
        before = (root / "data/candidates.json").read_bytes()
        with (
            patch(
                "url_lists.discovery.collect_github_code",
                side_effect=DiscoveryError("offline"),
            ),
            patch(
                "url_lists.discovery.collect_purl_definitions",
                side_effect=DiscoveryError("offline"),
            ),
            patch(
                "url_lists.discovery.collect_published_sources",
                side_effect=PublishedSourceError("offline"),
            ),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(DiscoveryError),
        ):
            run_network_discovery(root, token="test")
        self.assertEqual((root / "data/candidates.json").read_bytes(), before)

    def test_cached_llm_review_skips_transport_but_force_refreshes(self):
        root = self.make_root()

        def transport(*args, **kwargs):
            return {
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"summary": "No suggestions", "findings": []}
                            )
                        }
                    }
                ],
                "usage": {},
            }

        report = create_review_report(
            root, "deepseek", "test-model", "test", transport=transport
        )
        write_review_report(root, report)
        module = script("llm_review")
        args = ["llm_review", "--provider", "deepseek", "--model", "test-model"]
        with (
            patch.object(module, "ROOT", root),
            patch.object(sys, "argv", args),
            patch.object(module, "create_review_report", return_value=report) as create,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(module.main(), 0)
            create.assert_not_called()
            with patch.object(sys, "argv", [*args, "--force"]):
                self.assertEqual(module.main(), 0)
                create.assert_called_once()
            create.reset_mock()
            document = read_json(root / "data/candidates.json")
            document["candidates"][0]["categories"].append("javascript")
            write_json_atomic(root / "data/candidates.json", document)
            module.main()
            create.assert_called_once()

    def test_offline_traffic_report_preserves_path_boundaries_and_drops_credentials(
        self,
    ):
        catalog = {
            "entries": [
                {
                    "target": "shared.vendor.net/packages",
                    "match": "path",
                    "status": "approved",
                    "categories": ["python"],
                },
                {
                    "target": ".registry.vendor.net",
                    "match": "suffix",
                    "status": "approved",
                    "categories": ["jvm"],
                },
            ]
        }
        report = review_traffic(
            [
                {
                    "url": "https://shared.vendor.net/packages/a?token=secret",
                    "requests": 5,
                },
                "https://shared.vendor.net/packages-other",
                "https://a.registry.vendor.net/artifact",
                "https://registry.vendor.net.evil.net/",
                "https://user:secret@private.vendor.net/",
            ],
            catalog,
        )
        self.assertEqual(report["covered_requests"], 6)
        self.assertEqual(report["uncovered_requests"], 2)
        self.assertEqual(report["invalid_records"], 1)
        self.assertNotIn("secret", json.dumps(report))


class RateLimitTests(unittest.TestCase):
    def test_unhonored_rate_limit_defers_subsequent_queries(self):
        error = HTTPError(
            "https://api.github.com/search/code",
            429,
            "rate limit",
            {"Retry-After": "120"},
            None,
        )
        budget = _RetryBudget(90)
        with (
            patch("url_lists.discovery._OPENER.open", side_effect=error) as request,
            patch("url_lists.discovery.time.sleep") as sleep,
        ):
            for query in ("one", "two"):
                with self.assertRaises(DiscoveryError):
                    _get_bytes(
                        f"https://api.github.com/search/code?q={query}", budget=budget
                    )
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_server_wait_is_never_shortened(self):
        error = HTTPError(
            "https://api.github.com/search/code",
            429,
            "rate limit",
            {"Retry-After": "120"},
            None,
        )
        self.assertEqual(_retry_delay(error, 0), 120)
        with (
            patch("url_lists.discovery._OPENER.open", side_effect=error) as request,
            patch("url_lists.discovery.time.sleep") as sleep,
        ):
            with self.assertRaises(DiscoveryError):
                _get_bytes(error.url, budget=_RetryBudget(90))
        self.assertEqual(request.call_count, 1)
        sleep.assert_not_called()

    def test_403_rate_limits_and_permission_errors_are_distinguished(self):
        for headers, attempts in (
            ({"Retry-After": "0"}, 4),
            ({"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1020"}, 4),
            ({}, 1),
        ):
            with self.subTest(headers=headers):
                error = HTTPError(
                    "https://api.github.com/search/code",
                    403,
                    "Forbidden",
                    headers,
                    None,
                )
                with (
                    patch(
                        "url_lists.discovery._OPENER.open", side_effect=error
                    ) as request,
                    patch("url_lists.discovery.time.time", return_value=1000),
                    patch("url_lists.discovery.time.sleep"),
                ):
                    with self.assertRaises(DiscoveryError):
                        _get_bytes(error.url)
                self.assertEqual(request.call_count, attempts)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.catalog import read_json, write_json_atomic
from url_lists.cloudflare_intel import (
    CLOUDFLARE_CACHE,
    CLOUDFLARE_REVIEW_MARKDOWN,
    CloudflareIntelError,
    _normalize_result,
    enrich_candidates,
    empty_cache,
    fetch_domain_batch,
    validate_cache,
    write_review,
)


ACCOUNT_ID = "a" * 32


def classification(risk_score: float | None = 0.1) -> dict[str, object]:
    return {
        "application": {"id": 7, "name": "Package repository"},
        "content_categories": [
            {"id": 155, "name": "Technology", "super_category_id": 26}
        ],
        "inherited_content_categories": [],
        "inherited_from": None,
        "inherited_risk_types": [],
        "risk_score": risk_score,
        "risk_types": [],
        "suspected_malware_family": None,
    }


class FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.content = json.dumps(payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def read(self, maximum: int) -> bytes:
        return self.content[:maximum]


class CloudflareIntelTests(unittest.TestCase):
    def test_normalizes_documented_domain_intelligence_fields(self) -> None:
        domain, result = _normalize_result(
            {
                "domain": "packages.vendor.net",
                "application": {"id": 7, "name": "Package repository"},
                "content_categories": [
                    {"id": 155, "name": "Technology", "super_category_id": 26}
                ],
                "inherited_content_categories": [],
                "inherited_from": None,
                "inherited_risk_types": [],
                "risk_score": 0.2,
                "risk_types": [{"id": 3, "name": "New domain"}],
                "additional_information": {
                    "suspected_malware_family": "example-family"
                },
            }
        )
        self.assertEqual(domain, "packages.vendor.net")
        self.assertEqual(result["application"]["name"], "Package repository")
        self.assertEqual(result["content_categories"][0]["name"], "Technology")
        self.assertEqual(result["risk_score"], 0.2)
        self.assertEqual(result["suspected_malware_family"], "example-family")

    def test_optional_ids_can_be_absent(self) -> None:
        _, result = _normalize_result(
            {
                "domain": "packages.vendor.net",
                "application": {"name": "Package repository"},
                "content_categories": [{"name": "Technology"}],
                "risk_types": [],
            }
        )
        self.assertEqual(result["application"], {"name": "Package repository"})
        self.assertEqual(result["content_categories"], [{"name": "Technology"}])

    def test_bulk_request_disables_ranking_and_never_exceeds_twenty(self) -> None:
        domains = ["one.vendor.net", "two.vendor.net"]
        payload = {
            "success": True,
            "errors": [],
            "result": [
                {"domain": domain, "content_categories": [], "risk_types": []}
                for domain in domains
            ],
        }
        with patch(
            "url_lists.cloudflare_intel._OPENER.open",
            return_value=FakeResponse(payload),
        ) as opened:
            results = fetch_domain_batch(ACCOUNT_ID, "secret-token", domains)
        self.assertEqual(set(results), set(domains))
        request = opened.call_args.args[0]
        self.assertIn("domain=one.vendor.net", request.full_url)
        self.assertIn("domain=two.vendor.net", request.full_url)
        self.assertIn("include_ranking=false", request.full_url)
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        with self.assertRaises(CloudflareIntelError):
            fetch_domain_batch(ACCOUNT_ID, "secret-token", [f"h{i}.net" for i in range(21)])

    def test_rejects_invalid_account_id_before_request(self) -> None:
        with self.assertRaises(CloudflareIntelError):
            fetch_domain_batch("project-name", "secret-token", ["packages.vendor.net"])

    def test_enrichment_prioritizes_high_confidence_and_respects_call_cap(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture(root, count=25)
            requested: list[list[str]] = []

            def fetcher(account_id: str, token: str, domains):
                batch = list(domains)
                requested.append(batch)
                return {domain: classification() for domain in batch}

            report = enrich_candidates(
                root,
                account_id=ACCOUNT_ID,
                token="secret-token",
                max_calls=1,
                today=date(2026, 8, 23),
                fetcher=fetcher,
            )
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["calls_made"], 1)
            self.assertEqual(report["refreshed_domain_count"], 20)
            self.assertEqual(report["remaining_domain_count"], 5)
            self.assertTrue(requested[0][0].startswith("high"))
            cache = read_json(root / CLOUDFLARE_CACHE)
            self.assertEqual(len(cache["entries"]), 20)

    def test_recent_cache_entries_are_not_queried_again(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture(root, count=2)
            cache = empty_cache()
            first = classification()
            first["checked_on"] = "2026-08-22"
            cache["entries"]["high00.vendor.net"] = first
            write_json_atomic(root / CLOUDFLARE_CACHE, cache)
            requested = []

            def fetcher(account_id: str, token: str, domains):
                batch = list(domains)
                requested.extend(batch)
                return {domain: classification() for domain in batch}

            report = enrich_candidates(
                root,
                account_id=ACCOUNT_ID,
                token="secret-token",
                today=date(2026, 8, 23),
                fetcher=fetcher,
            )
            self.assertEqual(requested, ["low01.vendor.net"])
            self.assertEqual(report["status"], "ok")

    def test_successful_batches_survive_a_later_provider_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture(root, count=25)
            calls = 0

            def fetcher(account_id: str, token: str, domains):
                nonlocal calls
                calls += 1
                batch = list(domains)
                if calls == 2:
                    raise CloudflareIntelError("quota exhausted")
                return {domain: classification() for domain in batch}

            report = enrich_candidates(
                root,
                account_id=ACCOUNT_ID,
                token="secret-token",
                max_calls=2,
                today=date(2026, 8, 23),
                fetcher=fetcher,
            )
            self.assertEqual(report["status"], "partial")
            self.assertEqual(report["provider_error"], "quota exhausted")
            self.assertEqual(report["calls_made"], 2)
            self.assertEqual(report["remaining_domain_count"], 5)
            cache = read_json(root / CLOUDFLARE_CACHE)
            self.assertEqual(len(cache["entries"]), 20)

    def test_review_is_human_readable_and_cache_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self._write_fixture(root, count=1)
            cache = empty_cache()
            entry = classification(0.25)
            entry["checked_on"] = "2026-08-23"
            cache["entries"]["high00.vendor.net"] = entry
            write_json_atomic(root / CLOUDFLARE_CACHE, cache)
            report = {
                "schema_version": 1,
                "provider": "cloudflare-domain-intelligence",
                "status": "ok",
                "as_of": "2026-08-23",
                "candidate_domain_count": 1,
                "cached_domain_count": 1,
                "refreshed_domain_count": 1,
                "remaining_domain_count": 0,
                "calls_made": 1,
                "provider_error": None,
                "refreshed_domains": ["high00.vendor.net"],
            }
            write_review(root, report)
            markdown = (root / CLOUDFLARE_REVIEW_MARKDOWN).read_text()
            self.assertIn("Package repository", markdown)
            self.assertIn("Technology", markdown)
            self.assertEqual(validate_cache(cache), [])

    @staticmethod
    def _write_fixture(root: Path, *, count: int) -> None:
        candidates = []
        for index in range(count):
            confidence = "high" if index % 2 == 0 else "low"
            candidates.append(
                {
                    "target": f"{confidence}{index:02d}.vendor.net",
                    "confidence": confidence,
                }
            )
        write_json_atomic(
            root / "data" / "candidates.json",
            {"schema_version": 1, "candidates": candidates},
        )
        write_json_atomic(root / CLOUDFLARE_CACHE, empty_cache())


if __name__ == "__main__":
    unittest.main()

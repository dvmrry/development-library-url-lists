from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.llm_review import (
    PROVIDER_ENDPOINTS,
    ReviewError,
    _post_json,
    build_review_input,
    call_provider,
    create_review_report,
    validate_model_output,
    validate_review_files,
    write_review_report,
)


class LlmReviewTests(unittest.TestCase):
    def make_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        data = root / "data"
        data.mkdir()
        self.write_json(
            data / "categories.json",
            {
                "schema_version": 1,
                "categories": [
                    {"id": "python", "title": "Python", "filename": "python.txt"},
                    {
                        "id": "javascript",
                        "title": "JavaScript",
                        "filename": "javascript.txt",
                    },
                ],
            },
        )
        self.write_json(
            data / "catalog.json",
            {
                "schema_version": 1,
                "entries": [
                    {
                        "target": "registry.npmjs.org",
                        "match": "exact",
                        "categories": ["javascript"],
                        "kind": "canonical",
                        "status": "approved",
                        "evidence": ["https://docs.npmjs.com/cli/using-npm/registry"],
                    }
                ],
            },
        )
        self.write_json(
            data / "candidates.json",
            {
                "schema_version": 1,
                "candidates": [
                    {
                        "target": "mirror.example.org",
                        "categories": ["python"],
                        "confidence": "low",
                        "review_flags": [],
                        "sources": [
                            {
                                "source": "https://github.com/acme/project/blob/main/pip.conf",
                                "source_kind": "github-code",
                                "repository": "acme/project",
                            }
                        ],
                    }
                ],
            },
        )
        self.write_json(data / "rejections.json", {"schema_version": 1, "rejections": []})
        self.write_json(
            data / "search_queries.json",
            {
                "schema_version": 1,
                "queries": [
                    {
                        "id": "pip-index",
                        "ecosystem": "python",
                        "query": '"index-url" filename:pip.conf',
                        "extractor": "pip-config",
                        "max_results": 20,
                    }
                ],
            },
        )
        return root

    @staticmethod
    def write_json(path: Path, value: object) -> None:
        path.write_text(json.dumps(value), encoding="utf-8")

    @staticmethod
    def model_output() -> dict:
        return {
            "summary": "A hosted provider may be absent.",
            "findings": [
                {
                    "finding_type": "missing_provider",
                    "title": "Review Example Packages",
                    "confidence": "medium",
                    "categories": ["python"],
                    "proposed_categories": [],
                    "suggested_targets": [
                        {
                            "target": ".packages.example.com",
                            "match": "suffix",
                            "kind": "hosted-registry-provider",
                        },
                        {
                            "target": "registry.npmjs.org",
                            "match": "exact",
                            "kind": "canonical",
                        },
                    ],
                    "evidence_urls": ["https://example.com/package-documentation"],
                    "rationale": "The provider serves language package formats.",
                    "recommended_action": "Verify its documentation and hostname shape.",
                }
            ],
        }

    def test_builds_bounded_inventory_without_raw_source_content(self) -> None:
        bundle = build_review_input(self.make_root())
        self.assertEqual(bundle["categories"][0]["id"], "python")
        candidate = bundle["unapproved_candidates"][0]
        self.assertEqual(candidate["evidence_source_count"], 1)
        self.assertNotIn("content", json.dumps(bundle))

    def test_large_candidate_inventory_is_summarized_and_sampled(self) -> None:
        root = self.make_root()
        candidates = []
        for index in range(1_200):
            candidates.append(
                {
                    "target": f"mirror-{index:04d}.vendor.net",
                    "categories": ["python" if index % 2 else "javascript"],
                    "confidence": "high",
                    "review_flags": [],
                    "sources": [
                        {
                            "source": "https://cran.r-project.org/CRAN_mirrors.csv",
                            "source_ecosystem": "cran",
                            "source_kind": "published-list",
                            "repository": "r-project/cran-mirrors",
                        }
                    ],
                }
            )
        self.write_json(
            root / "data" / "candidates.json",
            {"schema_version": 1, "candidates": candidates},
        )
        bundle = build_review_input(root)
        self.assertEqual(bundle["candidate_summary"]["total"], 1_200)
        self.assertEqual(
            bundle["candidate_summary"]["by_source_ecosystem"],
            {"cran": 1_200},
        )
        self.assertEqual(len(bundle["unapproved_candidates"]), 300)
        self.assertEqual(len(bundle["candidate_targets"]), 1_200)
        self.assertLess(len(json.dumps(bundle).encode()), 500_000)

    def test_openai_request_uses_fixed_endpoint_and_structured_output(self) -> None:
        captured = {}

        def fake(url, headers, payload):
            captured.update(url=url, headers=headers, payload=payload)
            return {
                "output_text": json.dumps(self.model_output()),
                "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            }

        result = call_provider(
            "openai",
            "gpt-5.4-mini",
            "test-secret",
            build_review_input(self.make_root()),
            transport=fake,
        )
        self.assertEqual(captured["url"], PROVIDER_ENDPOINTS["openai"])
        self.assertEqual(captured["headers"]["Authorization"], "Bearer test-secret")
        self.assertTrue(captured["payload"]["text"]["format"]["strict"])
        self.assertEqual(result.usage["total_tokens"], 120)

    def test_deepseek_request_uses_json_mode_without_thinking(self) -> None:
        captured = {}

        def fake(url, headers, payload):
            captured.update(url=url, payload=payload)
            return {
                "choices": [{"message": {"content": json.dumps(self.model_output())}}],
                "usage": {"prompt_tokens": 90, "completion_tokens": 10},
            }

        result = call_provider(
            "deepseek",
            "deepseek-v4-flash",
            "test-secret",
            build_review_input(self.make_root()),
            transport=fake,
        )
        self.assertEqual(captured["url"], PROVIDER_ENDPOINTS["deepseek"])
        self.assertEqual(captured["payload"]["response_format"], {"type": "json_object"})
        self.assertEqual(captured["payload"]["thinking"], {"type": "disabled"})
        self.assertEqual(result.usage["total_tokens"], 100)

    def test_anthropic_and_gemini_responses_are_normalized(self) -> None:
        bundle = build_review_input(self.make_root())
        output = json.dumps(self.model_output())

        def anthropic(url, headers, payload):
            schema_text = json.dumps(payload["output_config"]["format"]["schema"])
            self.assertNotIn("maxLength", schema_text)
            return {
                "content": [{"type": "text", "text": output}],
                "usage": {"input_tokens": 80, "output_tokens": 20},
            }

        anthropic_result = call_provider(
            "anthropic",
            "claude-haiku-4-5",
            "test-secret",
            bundle,
            transport=anthropic,
        )
        self.assertEqual(anthropic_result.usage["total_tokens"], 100)

        def gemini(url, headers, payload):
            self.assertEqual(payload["response_format"]["mime_type"], "application/json")
            return {
                "steps": [
                    {
                        "type": "model_output",
                        "content": [{"type": "text", "text": output}],
                    }
                ],
                "usage": {
                    "total_input_tokens": 75,
                    "total_output_tokens": 25,
                    "total_tokens": 100,
                },
            }

        gemini_result = call_provider(
            "gemini",
            "gemini-3.7-flash",
            "test-secret",
            bundle,
            transport=gemini,
        )
        self.assertEqual(gemini_result.usage["total_tokens"], 100)

    def test_transport_retries_transient_provider_errors(self) -> None:
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            @staticmethod
            def read(limit):
                return b'{"result":"ok"}'

        busy = HTTPError(
            PROVIDER_ENDPOINTS["gemini"],
            500,
            "high demand",
            {},
            BytesIO(b'{"error":{"message":"high demand"}}'),
        )
        with (
            patch("url_lists.llm_review._OPENER.open", side_effect=[busy, FakeResponse()])
            as open_request,
            patch("url_lists.llm_review.time.sleep") as sleep,
        ):
            response = _post_json(PROVIDER_ENDPOINTS["gemini"], {}, {"test": True})

        self.assertEqual(response, {"result": "ok"})
        self.assertEqual(open_request.call_count, 2)
        sleep.assert_called_once_with(5)

    def test_validates_targets_and_marks_model_links_unverified(self) -> None:
        bundle = build_review_input(self.make_root())
        reviewed = validate_model_output(self.model_output(), bundle)
        finding = reviewed["findings"][0]
        self.assertEqual(finding["evidence_status"], "unverified")
        known = next(
            item
            for item in finding["suggested_targets"]
            if item["target"] == "registry.npmjs.org"
        )
        self.assertEqual(known["review_flags"], ["already-approved"])

    def test_rejects_private_evidence_url(self) -> None:
        output = self.model_output()
        output["findings"][0]["evidence_urls"] = ["https://127.0.0.1/internal"]
        with self.assertRaises(ReviewError):
            validate_model_output(output, build_review_input(self.make_root()))

    def test_creates_and_validates_persisted_review(self) -> None:
        root = self.make_root()

        def fake(url, headers, payload):
            return {
                "output_text": json.dumps(self.model_output()),
                "usage": {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
            }

        report = create_review_report(
            root,
            "openai",
            "gpt-5.4-mini",
            "test-secret",
            transport=fake,
            now=datetime(2026, 8, 23, 12, 0, tzinfo=timezone.utc),
        )
        write_review_report(root, report)
        self.assertEqual(validate_review_files(root), [])
        markdown = (root / "reviews" / "llm" / "latest.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Suggestion only", markdown)
        self.assertIn("unverified", markdown)


if __name__ == "__main__":
    unittest.main()

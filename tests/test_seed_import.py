from __future__ import annotations

import gzip
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.seed_import import (
    OBSERVATION_KEYS,
    SeedImportResult,
    collect_seed_observations,
    map_path_to_extractor,
    read_seed_records,
    run_seed_import,
)


class SeedImportIntegrationTests(unittest.TestCase):
    def test_import_applies_the_threshold_and_refreshes_the_review_queue(self) -> None:
        """A real import must not leave reviews/pending stale for validation."""

        import json
        import shutil
        import tempfile

        from url_lists.review_queue import validate_review_queue
        from url_lists.seed_import import run_seed_import

        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for relative in ("data", "reviews/pending"):
                (root / relative).mkdir(parents=True, exist_ok=True)
            for name in (
                "candidates.json",
                "catalog.json",
                "categories.json",
                "discovery_exclusions.json",
                "rejections.json",
            ):
                shutil.copy(repo_root / "data" / name, root / "data" / name)
            for name in ("queue.json", "domains.txt"):
                shutil.copy(
                    repo_root / "reviews" / "pending" / name,
                    root / "reviews" / "pending" / name,
                )

            seed = root / "seed.ndjson"
            records = []
            # One host reaching the threshold, one that never does.
            for index in range(6):
                records.append(
                    {
                        "repo_name": f"wide{index}/project",
                        "path": "pip.conf",
                        "content": (
                            f"[global]\nindex-url = https://widemirror.vendornet.org/simple\n"
                            f"# unique {index}\n"
                        ),
                    }
                )
            records.append(
                {
                    "repo_name": "acmecorp/only",
                    "path": "pip.conf",
                    "content": "[global]\nindex-url = https://internal.acmecorp.org/simple\n",
                }
            )
            seed.write_text("\n".join(json.dumps(r) for r in records) + "\n")

            run_seed_import(root, seed)

            targets = {
                candidate["target"]
                for candidate in json.loads(
                    (root / "data" / "candidates.json").read_text()
                )["candidates"]
            }
            self.assertIn("widemirror.vendornet.org", targets)
            self.assertNotIn("internal.acmecorp.org", targets)
            self.assertEqual(validate_review_queue(root), [])


class SeedRepositoryThresholdTests(unittest.TestCase):
    """A seed-only hostname must prove reach across independent repositories."""

    def test_seed_only_host_below_threshold_is_not_admitted(self) -> None:
        from url_lists.seed_import import apply_repository_threshold

        observations = [
            {
                "target": "internal-artifactory.acmecorp.net",
                "repository": "acmecorp/one",
                "source_kind": "bigquery-github",
            },
            {
                "target": "internal-artifactory.acmecorp.net",
                "repository": "acmecorp/two",
                "source_kind": "bigquery-github",
            },
        ]
        kept, dropped = apply_repository_threshold(
            observations, minimum_repositories=5, known_targets=set()
        )
        self.assertEqual(kept, [])
        self.assertEqual(dropped, {"internal-artifactory.acmecorp.net"})

    def test_seed_host_meeting_threshold_is_admitted(self) -> None:
        from url_lists.seed_import import apply_repository_threshold

        observations = [
            {
                "target": "mirror.vendor.net",
                "repository": f"org{index}/project",
                "source_kind": "bigquery-github",
            }
            for index in range(5)
        ]
        kept, dropped = apply_repository_threshold(
            observations, minimum_repositories=5, known_targets=set()
        )
        self.assertEqual(len(kept), 5)
        self.assertEqual(dropped, set())

    def test_repeated_repository_does_not_satisfy_the_threshold(self) -> None:
        """One noisy repository must not manufacture reach by itself."""

        from url_lists.seed_import import apply_repository_threshold

        observations = [
            {
                "target": "internal.acmecorp.net",
                "repository": "acmecorp/one",
                "source_kind": "bigquery-github",
            }
            for _ in range(50)
        ]
        kept, dropped = apply_repository_threshold(
            observations, minimum_repositories=5, known_targets=set()
        )
        self.assertEqual(kept, [])
        self.assertEqual(dropped, {"internal.acmecorp.net"})

    def test_already_known_target_bypasses_the_threshold(self) -> None:
        """A host vetted by another discovery path keeps its seed evidence."""

        from url_lists.seed_import import apply_repository_threshold

        observations = [
            {
                "target": "mirror.vendor.net",
                "repository": "acmecorp/one",
                "source_kind": "bigquery-github",
            }
        ]
        kept, dropped = apply_repository_threshold(
            observations,
            minimum_repositories=5,
            known_targets={"mirror.vendor.net"},
        )
        self.assertEqual(len(kept), 1)
        self.assertEqual(dropped, set())


class SeedImportTests(unittest.TestCase):
    def record(
        self,
        path: str,
        content: str = "index-url = https://packages.example.net/simple\n",
        repo_name: str = "acme/project",
    ) -> dict[str, str]:
        return {"repo_name": repo_name, "path": path, "content": content}

    def write_seed(
        self,
        directory: Path,
        records: list[object],
        *,
        suffix: str = ".jsonl",
    ) -> Path:
        path = directory / f"seed{suffix}"
        lines = [
            item if isinstance(item, str) else json.dumps(item)
            for item in records
        ]
        payload = ("\n".join(lines) + "\n").encode("utf-8")
        if suffix.endswith(".gz"):
            with gzip.open(path, "wb") as stream:
                stream.write(payload)
        else:
            path.write_bytes(payload)
        return path

    def test_well_formed_records_use_format_extractors_and_categories(self) -> None:
        records = [
            self.record(
                "config/pip.conf",
                "index-url = https://python.example.net/simple\n",
            ),
            self.record(
                "packages/.NPMRC",
                "registry=https://javascript.example.net/npm\n",
            ),
            self.record(
                "build/pom.XML",
                "<project><repositories><repository><url>"
                "https://maven.example.net/repository</url></repository>"
                "</repositories></project>",
            ),
            self.record(
                "dotnet/NUGET.CONFIG",
                "<configuration><packageSources><add key=\"mirror\" "
                "value=\"https://dotnet.example.net/v3/index.json\" />"
                "</packageSources></configuration>",
            ),
        ]

        result = collect_seed_observations(records)

        self.assertIsInstance(result, SeedImportResult)
        self.assertEqual(result.records_read, 4)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(result.observations_produced, 4)
        self.assertEqual(
            {observation["category"] for observation in result.observations},
            {"python", "javascript", "jvm", "dotnet"},
        )
        self.assertTrue(
            all(set(observation) == set(OBSERVATION_KEYS) for observation in result.observations)
        )
        npm_observation = next(
            item
            for item in result.observations
            if item["extractor"] == "npmrc"
        )
        self.assertEqual(npm_observation["discovered_url"], "https://javascript.example.net/npm")
        self.assertEqual(npm_observation["source_kind"], "bigquery-github")
        self.assertEqual(npm_observation["query_id"], "bigquery-github")
        self.assertEqual(npm_observation["repository"], "acme/project")
        self.assertEqual(
            npm_observation["content_sha256"],
            hashlib.sha256(records[1]["content"].encode("utf-8")).hexdigest(),
        )

    def test_gzip_seed_is_read_as_newline_delimited_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            seed_path = self.write_seed(
                Path(temporary),
                [
                    self.record(
                        "pip.ini",
                        "index-url = https://gzip.example.net/simple\n",
                    )
                ],
                suffix=".jsonl.gz",
            )

            result = read_seed_records(seed_path)

        self.assertEqual(result.records_read, 1)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(result.observations[0]["extractor"], "pip-config")

    def test_malformed_non_string_and_extraction_failure_are_counted_and_skipped(self) -> None:
        records: list[object] = [
            "{not-json",
            {"repo_name": "acme/project", "path": "pip.conf", "content": 7},
            self.record("broken/pip.conf"),
            self.record(
                "good/pip.conf",
                "index-url = https://good.example.net/simple\n",
            ),
        ]
        stderr = io.StringIO()
        with patch(
            "url_lists.seed_import.extract_registry_urls",
            side_effect=[RuntimeError("hostile parser input"), ["https://good.example.net/simple"]],
        ):
            result = collect_seed_observations(records, stderr=stderr)

        self.assertEqual(result.records_read, 4)
        self.assertEqual(result.skipped, 3)
        self.assertEqual(result.observations_produced, 1)
        self.assertEqual(result.observations[0]["repository"], "acme/project")
        warning = stderr.getvalue()
        self.assertEqual(warning.count("Seed record"), 3)
        self.assertIn("extraction failed", warning.lower())

    def test_unknown_path_is_skipped_instead_of_guessed(self) -> None:
        stderr = io.StringIO()
        result = collect_seed_observations(
            [
                self.record("notes/registry.txt"),
                self.record(
                    "config/requirements-dev.TXT",
                    "--index-url https://requirements.example.net/simple\n",
                ),
            ],
            stderr=stderr,
        )

        self.assertEqual(map_path_to_extractor("notes/registry.txt"), None)
        self.assertEqual(result.records_read, 2)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.observations_produced, 1)
        self.assertIn("no known extractor", stderr.getvalue())

    def test_known_filename_patterns_are_case_insensitive(self) -> None:
        expected = {
            ".NPMRC": "npmrc",
            "PIP.INI": "pip-config",
            ".CONDARC": "conda-yaml",
            "environment.YAML": "conda-yaml",
            "POM.XML": "maven-pom-xml",
            "SETTINGS.XML": "maven-settings-xml",
            "NuGet.Config": "nuget-xml",
            "paket.dependencies": "paket-dependencies",
            "requirements-dev.TXT": "pip-requirements",
            "pyproject.toml": "python-toml-sources",
            "Pipfile": "python-toml-sources",
            "package.json": "package-json-registry",
            ".yarnrc": "yarnrc-v1",
            ".yarnrc.YML": "yarnrc-yaml",
            "build.gradle": "gradle-repository",
            "build.gradle.kts": "gradle-repository",
            "module.SBT": "sbt-resolver",
            "Directory.Build.PROPS": "msbuild-restore-sources",
            "project.CSPROJ": "msbuild-restore-sources",
        }

        for path, extractor in expected.items():
            with self.subTest(path=path):
                self.assertEqual(map_path_to_extractor(f"nested/{path}"), extractor)

    def test_source_role_uses_existing_discovery_classifier(self) -> None:
        records = [
            self.record(
                "docs/setup/pip.conf",
                "index-url = https://docs-mirror.example.net/simple\n",
            ),
            self.record(
                "tests/fixtures/pip.conf",
                "index-url = https://test-mirror.example.net/simple\n",
            ),
            self.record(
                "examples/pip.conf",
                "index-url = https://example-mirror.example.net/simple\n",
            ),
        ]

        result = collect_seed_observations(records)

        self.assertEqual(
            [item["source_role"] for item in result.observations],
            ["documentation", "test", "example"],
        )

    def test_source_url_encodes_spaces_dot_segments_and_controls(self) -> None:
        hostile_path = "dir with space/../configs\x01/pip.conf"
        result = collect_seed_observations(
            [self.record(hostile_path, repo_name="owner/project")]
        )

        self.assertEqual(result.skipped, 0)
        self.assertEqual(
            result.observations[0]["source"],
            "https://github.com/owner/project/blob/HEAD/"
            "dir%20with%20space/%2E%2E/configs%01/pip.conf",
        )
        self.assertNotIn(" ", result.observations[0]["source"])
        self.assertNotIn("\x01", result.observations[0]["source"])

    def test_enormous_content_is_skipped_without_calling_extractor(self) -> None:
        stderr = io.StringIO()
        with patch("url_lists.seed_import.extract_registry_urls") as extractor:
            result = collect_seed_observations(
                [self.record("pip.conf", "x" * (2_000_001))],
                stderr=stderr,
            )

        extractor.assert_not_called()
        self.assertEqual(result.records_read, 1)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.observations_produced, 0)
        self.assertIn("too large", stderr.getvalue().lower())

    def test_run_seed_import_filters_merges_and_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            data = root / "data"
            data.mkdir()
            (data / "categories.json").write_bytes(
                (ROOT / "data" / "categories.json").read_bytes()
            )
            (data / "discovery_exclusions.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "exact_hosts": [],
                        "suffixes": [],
                        "shared_hosts": [],
                    }
                ),
                encoding="utf-8",
            )
            (data / "rejections.json").write_text(
                json.dumps({"schema_version": 1, "rejections": []}),
                encoding="utf-8",
            )
            (data / "catalog.json").write_text(
                json.dumps({"schema_version": 1, "entries": []}),
                encoding="utf-8",
            )
            candidates_path = data / "candidates.json"
            candidates_path.write_text(
                json.dumps({"schema_version": 1, "candidates": []}),
                encoding="utf-8",
            )
            seed_path = self.write_seed(
                root,
                [
                    self.record(
                        "config/pip.conf",
                        "index-url = https://new.vendor.net/simple\n",
                    )
                ],
            )
            before = candidates_path.read_bytes()

            dry_run = run_seed_import(
                root, seed_path, dry_run=True, minimum_repositories=1
            )

            self.assertEqual(dry_run.records_read, 1)
            self.assertEqual(dry_run.observations_produced, 1)
            self.assertEqual(dry_run.candidates_added, 1)
            self.assertEqual(candidates_path.read_bytes(), before)

            applied = run_seed_import(root, seed_path, minimum_repositories=1)
            written = json.loads(candidates_path.read_text(encoding="utf-8"))

        self.assertEqual(applied.candidates_added, 1)
        self.assertEqual(written["candidates"][0]["target"], "new.vendor.net")
        self.assertEqual(
            written["candidates"][0]["sources"][0]["source_kind"],
            "bigquery-github",
        )

    def test_cli_dry_run_prints_summary_without_writing_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            seed_path = self.write_seed(
                Path(temporary),
                [
                    self.record(
                        "config/pip.conf",
                        "index-url = https://cli-mirror.vendor.net/simple\n",
                    )
                ],
            )
            candidates_path = ROOT / "data" / "candidates.json"
            before = candidates_path.read_bytes()
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "import_seed.py"),
                    "--dry-run",
                    "--min-repositories",
                    "1",
                    str(seed_path),
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Dry run complete; no files written;", completed.stdout)
        self.assertIn("records read: 1", completed.stdout)
        self.assertIn("skipped: 0", completed.stdout)
        self.assertIn("observations produced: 1", completed.stdout)
        self.assertIn("candidates added: 1", completed.stdout)
        self.assertEqual(completed.stderr, "")
        self.assertEqual(candidates_path.read_bytes(), before)

    def test_hostile_extracted_url_cannot_abort_the_merge(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            seed_path = self.write_seed(
                Path(temporary),
                [
                    self.record(
                        "bad/pip.conf",
                        "index-url = https://exa℀mple.com/simple\n",
                    ),
                    self.record(
                        "good/pip.conf",
                        "index-url = https://surviving.vendor.net/simple\n",
                    ),
                ],
            )
            stderr = io.StringIO()

            result = run_seed_import(
                ROOT,
                seed_path,
                dry_run=True,
                minimum_repositories=1,
                stderr=stderr,
            )

        self.assertEqual(result.records_read, 2)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.observations_produced, 2)
        self.assertEqual(result.candidates_added, 1)
        self.assertIn("recovering individually", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

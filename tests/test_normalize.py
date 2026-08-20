from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.normalize import TargetError, extract_urls, normalize_target, target_hostname


class NormalizeTests(unittest.TestCase):
    def test_normalizes_url_and_removes_query(self) -> None:
        self.assertEqual(
            normalize_target("HTTPS://Registry.NPMJS.org:443/foo/?token=nope"),
            "registry.npmjs.org/foo",
        )

    def test_normalizes_suffix(self) -> None:
        self.assertEqual(normalize_target(".JFROG.io"), ".jfrog.io")

    def test_can_reduce_url_to_host(self) -> None:
        self.assertEqual(
            normalize_target("https://mirror.example.org/simple/", preserve_path=False),
            "mirror.example.org",
        )

    def test_extracts_urls_without_markdown_punctuation(self) -> None:
        self.assertEqual(
            extract_urls("Use (https://packages.example.org/v1), not HTTP://old.example.net."),
            ["https://packages.example.org/v1", "HTTP://old.example.net"],
        )

    def test_rejects_credentials_wildcards_and_private_addresses(self) -> None:
        for value in (
            "https://user:pass@example.org/",
            "*.example.org",
            "http://127.0.0.1/repo",
            "localhost",
        ):
            with self.subTest(value=value):
                with self.assertRaises(TargetError):
                    normalize_target(value)

    def test_extracts_hostname_from_target(self) -> None:
        self.assertEqual(target_hostname("repo.example.org:8443/path"), "repo.example.org")


if __name__ == "__main__":
    unittest.main()

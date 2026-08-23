from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from url_lists.extractors import extract_registry_urls


class ExtractorTests(unittest.TestCase):
    def test_maven_uses_repository_fields_not_every_url_element(self) -> None:
        content = """
<project>
  <url>https://project.example.net</url>
  <licenses><license><url>https://www.opensource.org/licenses/mit</url></license></licenses>
  <repositories>
    <repository><url>https://packages.acme.net/maven</url></repository>
  </repositories>
  <distributionManagement>
    <repository><url>https://releases.acme.net/maven</url></repository>
  </distributionManagement>
</project>
"""
        self.assertEqual(
            extract_registry_urls(content, "maven-pom-xml"),
            [
                "https://packages.acme.net/maven",
                "https://releases.acme.net/maven",
            ],
        )

    def test_stack_package_indices_ignore_unrelated_documentation_urls(self) -> None:
        content = """
package-indices:
  - name: Hackage
    download-prefix: https://mirror.acme.net/package/
hackage-base-url: https://hackage.example.com/
documentation: https://docs.haskellstack.org/
reference: https://en.wikipedia.org/wiki/Haskell
"""
        self.assertEqual(
            extract_registry_urls(content, "stack-yaml"),
            ["https://mirror.acme.net/package/"],
        )

    def test_sbt_single_line_resolver_does_not_capture_the_next_line(self) -> None:
        content = """
resolvers += "Acme" at "https://packages.acme.net/sbt"
documentation := "https://docs.acme.net/sbt"
"""
        self.assertEqual(
            extract_registry_urls(content, "sbt-resolver"),
            ["https://packages.acme.net/sbt"],
        )

    def test_sbt_ignores_commented_resolvers(self) -> None:
        content = """
/* resolvers += "Old" at "https://old.acme.net/sbt" */
resolvers += "Acme" at "https://packages.acme.net/sbt" // https://docs.acme.net/sbt
"""
        self.assertEqual(
            extract_registry_urls(content, "sbt-resolver"),
            ["https://packages.acme.net/sbt"],
        )

    def test_gradle_repository_block_ends_before_unrelated_urls(self) -> None:
        content = """
repositories {
  maven {
    url = uri("https://packages.acme.net/maven") }
  documentation = "https://docs.acme.net/build"
}
"""
        self.assertEqual(
            extract_registry_urls(content, "gradle-repository"),
            ["https://packages.acme.net/maven"],
        )

    def test_gradle_ignores_block_and_inline_comment_urls(self) -> None:
        content = """
/* maven { url = "https://commented.acme.net/maven" } */
repositories {
  maven {
    url = "https://packages.acme.net/maven" // https://docs.acme.net/maven
  }
}
"""
        self.assertEqual(
            extract_registry_urls(content, "gradle-repository"),
            ["https://packages.acme.net/maven"],
        )

    def test_composer_ignores_vcs_and_project_urls(self) -> None:
        content = """
{
  "homepage": "https://project.example.net",
  "repositories": [
    {"type": "vcs", "url": "https://github.com/acme/project"},
    {"type": "composer", "url": "https://packages.acme.net/composer"}
  ]
}
"""
        self.assertEqual(
            extract_registry_urls(content, "composer-json"),
            ["https://packages.acme.net/composer"],
        )

    def test_docker_uses_only_registry_mirrors(self) -> None:
        content = """
{
  "registry-mirrors": ["https://containers.acme.net"],
  "proxies": {"https-proxy": "https://proxy.acme.net"}
}
"""
        self.assertEqual(
            extract_registry_urls(content, "docker-json"),
            ["https://containers.acme.net"],
        )

    def test_docker_supports_a_templated_mirror_array(self) -> None:
        content = """
{
{% if ENABLE_MIRRORS %}
  "registry-mirrors": [
    "https://containers-one.acme.net",
    "https://containers-two.acme.net"
  ],
{% endif %}
  "https-proxy": "https://proxy.acme.net"
}
"""
        self.assertEqual(
            extract_registry_urls(content, "docker-json"),
            [
                "https://containers-one.acme.net",
                "https://containers-two.acme.net",
            ],
        )

    def test_environment_assignment_uses_only_the_named_value(self) -> None:
        content = """
export GOPROXY="https://proxy-one.acme.net,direct"
HELP_URL=https://docs.acme.net/go
set GOPROXY=https://proxy-two.acme.net|https://fallback.acme.net
"""
        self.assertEqual(
            extract_registry_urls(
                content,
                "environment-assignment",
                keys=["GOPROXY"],
            ),
            [
                "https://proxy-one.acme.net",
                "https://proxy-two.acme.net",
                "https://fallback.acme.net",
            ],
        )

    def test_conda_reads_channel_alias_default_and_custom_channels(self) -> None:
        content = """
channels:
  - defaults
channel_alias: https://conda.acme.net/
default_channels:
  - https://conda.acme.net/pkgs/main
custom_channels:
  conda-forge: https://community.acme.net/cloud
proxy_servers:
  https: https://proxy.acme.net
"""
        self.assertEqual(
            extract_registry_urls(content, "conda-yaml"),
            [
                "https://conda.acme.net/",
                "https://conda.acme.net/pkgs/main",
                "https://community.acme.net/cloud",
            ],
        )

    def test_toml_extractors_ignore_unrelated_urls(self) -> None:
        uv_content = """
[project]
homepage = "https://project.example.net"
[[tool.uv.index]]
url = "https://python.acme.net/simple"
"""
        cargo_content = """
[package]
homepage = "https://project.example.net"
[source.crates-io]
replace-with = "acme"
[source.acme]
registry = "sparse+https://rust.acme.net/index/"
"""
        self.assertEqual(
            extract_registry_urls(uv_content, "uv-toml"),
            ["https://python.acme.net/simple"],
        )
        self.assertEqual(
            extract_registry_urls(cargo_content, "cargo-toml"),
            ["https://rust.acme.net/index/"],
        )

    def test_nuget_reads_only_package_source_values(self) -> None:
        content = """
<configuration>
  <packageSources>
    <add key="Acme" value="https://dotnet.acme.net/v3/index.json" />
  </packageSources>
  <config><add key="docs" value="https://docs.acme.net/nuget" /></config>
</configuration>
"""
        self.assertEqual(
            extract_registry_urls(content, "nuget-xml"),
            ["https://dotnet.acme.net/v3/index.json"],
        )

    def test_r_reads_only_the_repos_option_value(self) -> None:
        content = """
options(
  repos = c(CRAN = "https://r.acme.net/cran", BioC = "https://r.acme.net/bioc"),
  help.url = "https://docs.acme.net/r"
)
"""
        self.assertEqual(
            extract_registry_urls(content, "r-repositories"),
            ["https://r.acme.net/cran", "https://r.acme.net/bioc"],
        )

    def test_r_reads_a_named_repository_assignment(self) -> None:
        content = """
options(repos = normalize_repositories())
repos[["R-Forge"]] <- "https://r-forge.acme.net"
documentation <- "https://docs.acme.net/r"
"""
        self.assertEqual(
            extract_registry_urls(content, "r-repositories"),
            ["https://r-forge.acme.net"],
        )

    def test_xml_extractors_reject_entity_declarations(self) -> None:
        content = """
<!DOCTYPE project [<!ENTITY repo "https://packages.acme.net/maven">]>
<project><repositories><repository><url>&repo;</url></repository></repositories></project>
"""
        self.assertEqual(extract_registry_urls(content, "maven-pom-xml"), [])

    def test_environment_assignment_ignores_empty_values(self) -> None:
        content = "GOPROXY= \nGOPROXY=\nGOPROXY=\t\nGOPROXY=''\nGOPROXY=\"\"\n"
        self.assertEqual(
            extract_registry_urls(
                content,
                "environment-assignment",
                keys=["GOPROXY"],
            ),
            [],
        )

    def test_r_pathological_unbalanced_calls_complete_quickly(self) -> None:
        # Regression: repeated unbalanced "options(" once scanned to the end
        # of the file for every match (quadratic; ~34s for 8,000 repetitions
        # on the reference machine, ~136s for this fixture). The bounded scan
        # finishes in well under a second, so the 10-second budget holds a
        # margin of more than an order of magnitude in both directions even
        # on slow CI hardware.
        content = "options(repos\n" * 16_000
        start = time.perf_counter()
        result = extract_registry_urls(content, "r-repositories")
        elapsed = time.perf_counter() - start
        self.assertEqual(result, [])
        self.assertLess(elapsed, 10.0)

    def test_r_balanced_calls_still_extract_after_scan_bound(self) -> None:
        content = (
            "noise <- 1\n" * 200
            + 'options(repos = c(CRAN = "https://r.acme.net/cran"))\n'
        )
        self.assertEqual(
            extract_registry_urls(content, "r-repositories"),
            ["https://r.acme.net/cran"],
        )

    def test_pip_multiline_extra_indexes_are_bounded_to_the_setting(self) -> None:
        content = """
[global]
extra-index-url =
  https://python-one.acme.net/simple
  https://python-two.acme.net/simple
documentation = https://docs.acme.net/python
"""
        self.assertEqual(
            extract_registry_urls(content, "pip-config"),
            [
                "https://python-one.acme.net/simple",
                "https://python-two.acme.net/simple",
            ],
        )


if __name__ == "__main__":
    unittest.main()

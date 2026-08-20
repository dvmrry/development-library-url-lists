# Development Library URL Lists

[![Validate](https://github.com/dvmrry/development-library-url-lists/actions/workflows/validate.yml/badge.svg)](https://github.com/dvmrry/development-library-url-lists/actions/workflows/validate.yml)

Evidence-backed lists of public package repositories, mirrors, hosted registry
providers, and artifact-distribution endpoints.

The intended control is simple: developer endpoints are denied for normal
clients, while an internal Artifactory instance is the only system permitted to
retrieve and scan external packages. This repository maintains the reference
data; it does not connect to or change a Zscaler tenant.

## Outputs

Generated files live in `dist/`:

- `all.txt` contains every approved target.
- One plain-text file is published for each ecosystem, including Python,
  JavaScript, JVM, .NET, Rust, Go, PHP, Ruby, C/C++, Dart, Erlang/Elixir,
  Haskell, R, Julia, Swift, containers, and multi-ecosystem providers.
- `catalog.json` retains category, match type, status, kind, and evidence.
- `manifest.json` and `SHA256SUMS` provide counts and integrity hashes.

Targets are lowercase and scheme-free. A leading period represents a provider
suffix, for example `.jfrog.io`. Asterisks are never emitted.

## Automated discovery

The weekly GitHub Actions job uses only Python's standard library and the
repository's built-in `GITHUB_TOKEN`. It:

1. Searches public code for 27 package-manager settings, including npm, Yarn,
   pip, uv, Conda, Maven, Gradle, NuGet, Cargo, Go, Composer, RubyGems, Conan,
   Dart, Hex, Haskell, R, Julia, CocoaPods, Swift registries, and OCI mirrors.
2. Reads default repositories from the official Package-URL definitions.
3. Extracts and normalizes public hostnames.
4. Removes private/test/shared infrastructure and targets already covered by
   the curated catalog.
5. Merges new evidence into `data/candidates.json`.
6. Tests the result and opens or updates an automation pull request.

The collectors contact only `api.github.com` and
`raw.githubusercontent.com`. Discovered URLs are parsed but never fetched,
so a malicious public config cannot turn the workflow into an SSRF primitive.

## Approval model

Discovery never edits a published block list directly. A candidate needs human
review and promotion:

~~~console
python scripts/promote.py mirror.example.org --category python
~~~

Promotion records the discovery evidence, removes the review candidate, and
regenerates `dist/`. Entries are never removed automatically; a retired
endpoint remains in the evidence catalog with status `retired`.

This intentionally favors false negatives in published policy over silently
blocking an unrelated hostname because it appeared in an untrusted config.

## Local verification

Python 3.11 or later is sufficient. There are no runtime dependencies.

~~~console
python scripts/render.py
python -m unittest discover -s tests -v
python scripts/validate.py
~~~

To exercise the network collectors:

~~~console
GITHUB_TOKEN=... python scripts/update.py --network
~~~

On PowerShell:

~~~powershell
$env:GITHUB_TOKEN = "..."
python scripts/update.py --network
~~~

## Cost

The spike requires no paid service:

- public-repository GitHub Actions usage;
- GitHub's authenticated API through the workflow token;
- official Package-URL data;
- Python's standard library.

An LLM can later rank or summarize candidates, but it should never be the
authority that promotes or removes a network-policy target. No LLM or external
API key is part of this spike.

## Limits

No public feed can enumerate private or unindexed mirrors completely. GitHub
search is ranked and rate-limited, shared cloud hostnames require path-aware
judgment, and provider endpoints can be tenant-generated. Treat these lists as
a maintained input to defense in depth, not as proof of complete coverage.

Before enforcing them, compare the lists with current build traffic and verify
that the internal artifact service has every required upstream endpoint.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Each curated addition needs a category,
match mode, endpoint kind, and at least one public evidence URL.

MIT licensed.

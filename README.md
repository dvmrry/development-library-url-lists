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
  Haskell, R, Julia, Swift, containers, operating-system packages, and
  multi-ecosystem providers.
- `catalog.json` retains category, match type, status, kind, and evidence.
- `manifest.json` and `SHA256SUMS` provide counts and integrity hashes.
- `reviews/pending/domains.txt` and `queue.json` provide a minimal handoff for
  private Cloudflare and Zscaler review without publishing either vendor's
  response data.

Targets are lowercase and scheme-free. A leading period represents a provider
suffix, for example `.jfrog.io`. Asterisks are never emitted.

## Automated discovery

The weekly GitHub Actions job uses only Python's standard library and the
repository's built-in `GITHUB_TOKEN`. It:

1. Searches public code for package-manager settings across npm, Yarn,
   pip, uv, Conda, Maven, Gradle, NuGet, Cargo, Go, Composer, RubyGems, Conan,
   Dart, Hex, Haskell, R, Julia, CocoaPods, Swift registries, and OCI mirrors.
2. Reads default repositories from the official Package-URL definitions.
3. Reads published registry and mirror catalogs from ecosyste.ms, MirrorZ,
   CRAN, Alpine, Arch Linux, and Debian.
4. Parses only package-manager-specific configuration fields and normalizes
   their public hostnames.
5. Removes private/test/shared infrastructure, obvious documentation and
   placeholder targets, and targets already covered by the curated catalog.
6. Records extractor, source path, source role, ecosystem, and content hash provenance in
   `data/candidates.json`, then scores independent, non-identical configuration
   evidence.
7. Exports a minimal queue for a private Cloudflare/Zscaler pass and optionally
   asks one configured LLM for suggestion-only coverage gaps.
8. Tests the result and opens or updates an automation pull request.

Collectors contact only the fixed source hosts documented in
[`docs/data-sources.md`](docs/data-sources.md). Discovered URLs are parsed but
never fetched, so a malicious public config or catalog record cannot turn the
workflow into an SSRF primitive.

Every search query names a deterministic extractor for its actual format, such
as a Maven XML path, Cargo TOML field, or Docker JSON key. Generic line-wide
URL matching is rejected by validation. Documentation, examples, and tests may
preserve useful evidence but cannot raise confidence by repetition. A discovery
rules fingerprint rebuilds the candidate snapshot after extraction or filtering
logic changes, preventing older noisy results from surviving a stricter rule set.

## Approval model

Discovery never edits a published block list directly. A candidate needs human
review. Promote a real repository:

~~~console
python scripts/promote.py mirror.example.org --category python
~~~

Reject an unrelated or placeholder host so future runs keep it suppressed:

~~~console
python scripts/reject.py docs.example.org --reason "documentation site"
~~~

Promotion records the discovery evidence, removes the review candidate, and
regenerates `dist/`. Rejection preserves its evidence and rationale in
`data/rejections.json`. Deterministic flags identify documentation-like,
placeholder-like, nonstandard-port, retired-service, and non-configuration-only
candidates to speed up review.

Published entries are never removed automatically; a retired
endpoint remains in the evidence catalog with status `retired`.

This intentionally favors false negatives in published policy over silently
blocking an unrelated hostname because it appeared in an untrusted config.

## Optional LLM review

An opt-in pre-PR reviewer supports OpenAI, Anthropic, Gemini, and DeepSeek. It
receives a compact inventory, returns strictly validated suggestions, and writes
`reviews/llm/latest.json` plus a human-readable Markdown report into the
automation PR. It never edits the catalog, promotes a candidate, fetches a
suggested URL, or changes a Zscaler rule.

The feature is off unless a repository variable selects a provider and the
matching API-key secret is present. Provider failures do not stop deterministic
discovery. Every suggested evidence link is marked unverified. See
[the setup, provider comparison, and review contract](docs/llm-review.md).

## Optional Cloudflare enrichment

Cloudflare Domain Intelligence adds a second opinion about each candidate's
application, content categories, inherited categories, risk score, and risk
types. It is enrichment evidence only and cannot promote, reject, or edit a
target.

The public workflow deliberately does **not** publish Cloudflare responses.
Cloudflare's current Cloudforce One terms restrict third-party disclosure of
API-delivered threat intelligence, while public redistribution rights for the
ordinary Domain Intelligence response are not explicit. The repository
therefore writes `reviews/pending/domains.txt` and
`reviews/pending/queue.json`, which can feed a private runner or a local work
device. Detailed Cloudflare results are cached only beneath the gitignored
`.private/` directory.

For that private execution, create a least-privilege custom API token with
`Account > Intel > Read`, scoped to the intended account, and expose:

- `CLOUDFLARE_API_TOKEN` as a secret;
- `CLOUDFLARE_ACCOUNT_ID` as a variable.

The helper uses the bulk endpoint in groups of at most 20, disables ranking,
caps itself at 20 API calls per run, and caches results for 90 days. Successful
batches are retained even if a later batch fails.

Free, Pro, and Business accounts currently receive 100 Security Intelligence
API calls per month. The call cap and private cache are designed around that
budget. Cloudflare setup, terms, and API references are listed in
[`docs/data-sources.md`](docs/data-sources.md).

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

To run Cloudflare enrichment on a private runner or locally, set
`CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID`, then run:

~~~console
python scripts/enrich_cloudflare.py --max-calls 20 --stale-days 90
~~~

## Cost

The spike requires no paid service:

- public-repository GitHub Actions usage;
- GitHub's authenticated API through the workflow token;
- official Package-URL data;
- public registry and mirror catalogs;
- Python's standard library.

Private Cloudflare enrichment requires an account and API token but is designed
around the ordinary account quota. The optional LLM review is disabled by
default. If enabled, provider usage follows that provider's API pricing or
free-tier terms. Neither enrichment provider is the authority that promotes or
removes a network-policy target.

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

The repository code is MIT licensed. Source-derived data retains any applicable
upstream terms and attribution; see [`docs/data-sources.md`](docs/data-sources.md).

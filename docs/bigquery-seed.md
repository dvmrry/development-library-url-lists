# BigQuery seed extraction

GitHub code search is the recurring discovery path, but it has a fixed ceiling:
it permits roughly ten requests per minute and returns at most 1000 results for
one query. Adding more query patterns does not create more volume after those
limits are reached. The public GitHub dataset in BigQuery is therefore an
infrequent seed source, not a replacement feed. A person produces the seed out
of band and imports a file; the weekly workflow remains standard-library-only
and needs no Google Cloud credentials.

## First pull: separate from Gemini and from CI

This source uses ordinary SQL over public GitHub data, with no Gemini or other
model calls. A paid Gemini subscription is not required. Google's
[BigQuery sandbox](https://docs.cloud.google.com/bigquery/docs/sandbox) supports
public-data queries without a billing account, subject to its own quotas.
The documented compute allowance is 1 TiB per month; sandbox storage also has a
10 GiB lifetime limit that deletion does not refund. Check current project usage
before running anything; do not enable billing merely to follow this guide.

The importer being present does not mean a seed has been collected. The first
real pull requires a selected Google Cloud project, authorized BigQuery access,
a current scan estimate, and a complete downloaded seed. None of these are
configured by the weekly workflow.

Use the saved queries under [`queries/bigquery/`](../queries/bigquery/):

1. Inspect `metadata.sql` and the table schemas in the BigQuery console. Record
   table timestamps and sizes; confirm the `repo_name`, `path`, `id`, `content`,
   and `binary` fields used by the extraction query exist.
2. Paste `tier-a-select.sql` into the console and inspect its validator's byte
   estimate **before clicking Run**. With an authenticated Google Cloud CLI,
   the dry-run command below is an alternative.
3. Choose a maximum-bytes-billed cap that fits the remaining allowance. In the
   console use **Query settings > Advanced options > Maximum bytes billed**.
   On a billing-enabled project, stop for explicit spend approval if the query
   would exceed the free allowance. A per-job cap is not a monthly budget.
4. Run Tier A once only after that check. Save the results as **local
   newline-delimited JSON** under `.private/bigquery/`. No Cloud Storage bucket
   is needed for a result that fits the console's download limits. Check the
   downloaded record count against the job's total result rows; never treat a
   truncated download as a complete seed. See [saving query results](https://docs.cloud.google.com/bigquery/docs/writing-results#downloading_and_saving_query_results_from_the_console).
5. Import locally using the commands below. Review yield before considering
   Tier B, the full `contents` table, or any repeat schedule.

Keep the job ID, project, extraction time, table metadata, exact SQL, estimate,
maximum-bytes cap, actual bytes billed, total result rows, and original seed in
the same private run directory. This records what was actually queried and
prevents a historical snapshot from being mistaken for live GitHub coverage.

## Check freshness before scanning content

The `bigquery-public-data.github_repos` dataset was documented in 2017 as
refreshing weekly. That schedule is not verified today, and the available
dataset may be a stale snapshot. Check the table metadata before estimating or
running a content query:

Use [`metadata.sql`](../queries/bigquery/metadata.sql). Table modification times
are a freshness signal, not proof that each file is current.

An old snapshot still yields useful positive evidence because registry
hostnames tend to be long-lived. Absence is not evidence: a hostname missing
from the snapshot may have been added to GitHub later. If the metadata is stale
or the refresh schedule cannot be established, treat the result as a one-time
seed and do not repeat the pull as though it were a current feed.

## Cost mechanics

BigQuery bills on the columns scanned, not on the number of rows returned. A
`WHERE` clause can reduce the result while leaving the cost of a selected
column unchanged. In particular, selecting `content` scans the whole content
column that the query touches even when the path filter keeps only a small
number of files.

Always dry-run the exact query before executing it. `bq query --dry_run` and
the console byte estimator report the query's scan size without running the
query or incurring a charge. This is an estimate, not a guaranteed exact bill;
the tables can also change between estimation and execution. Pair it with an
enforced maximum-bytes-billed cap. See Google's [cost controls](https://docs.cloud.google.com/bigquery/docs/best-practices-costs).
For the saved query, with `YOUR_PROJECT_ID` replaced explicitly:

~~~console
bq --project_id=YOUR_PROJECT_ID query --location=US --use_legacy_sql=false --dry_run < queries/bigquery/tier-a-select.sql
~~~

Dry-run the bare `SELECT`, not the `EXPORT DATA` wrapper. A dry run reports the
scan estimate for a query; a scripting statement such as `EXPORT DATA` may
return no useful byte figure, which reads as reassuringly small rather than as
unmeasured. Keep a copy of each query with the export wrapper removed for this
purpose.

Start with `github_repos.sample_contents`, documented as a ten-percent sample;
do not assume it or its join with `files` fits the remaining free allowance.
Run Tier A there first if its estimate fits the chosen cap, then use its
yield to decide whether Tier B is warranted. Only replace
`sample_contents` with the full `contents` table after the sample produces
enough distinct, usable registry evidence to justify the larger scan, and
dry-run that changed query again. A path predicate does not make selecting the
full `content` column cheap.

## Stage the extraction

The two tiers put high-signal evidence ahead of the common files that produce
the largest export. Both saved queries are bare SELECTs for direct dry runs
and console downloads. They do not create tables or export to a bucket.

### Tier A: rare configuration files

Tier A selects filenames that are uncommon enough to keep the first export
small while still carrying package-manager registry settings: `.npmrc`,
`.yarnrc`, `.yarnrc.yml`, `pip.conf`, `pip.ini`, `.condarc`,
`environment.yml`, `environment.yaml`, `settings.xml`, `NuGet.Config`,
`paket.dependencies`, `Pipfile`, and `bunfig.toml`.

Use [`tier-a-select.sql`](../queries/bigquery/tier-a-select.sql).

The path expression is anchored at the basename so a similarly named file in
another path or a filename with an added suffix does not expand the export.
Binary rows are excluded because the repository's text extractors cannot
interpret them as package-manager configuration. The test is `IS NOT TRUE`
rather than `= FALSE` because the column is nullable, and an equality test
would silently discard every row whose flag is unset.

The pattern is case-insensitive. `REGEXP_CONTAINS` is case-sensitive by
default, and the same configuration file appears in public code as
`NuGet.Config`, `nuget.config`, and `NuGet.config`; a case-sensitive pattern
would miss most of them.

### Tier B: common configuration files

Tier B adds the common, high-volume names: `package.json`, `pom.xml`,
`requirements*.txt`, `pyproject.toml`, `build.gradle`, `build.gradle.kts`,
`*.csproj`, and `Directory.Packages.props`. Use it only after Tier A has
demonstrated that the seed is producing useful evidence.

Use [`tier-b-select.sql`](../queries/bigquery/tier-b-select.sql).

To use the full dataset, change only the `sample_contents` table reference to
`contents` after the dry run and yield review described above. Keeping the
queries otherwise identical makes the sample result a meaningful estimate of
which filenames and ecosystems warrant the full pass.

### Large results

If a complete console download is unavailable, stop and plan a separate export
to a private, access-controlled Cloud Storage bucket. Account for storage and
transfer costs, not just query bytes. Use a unique run prefix rather than
overwriting an earlier seed. Dry-run the bare SELECT, as described above, before
wrapping it in `EXPORT DATA`.

An export can produce multiple JSONL shards. Combine **all** shards from that
one job into one newline-delimited seed before import. Importing shards one at
a time applies the minimum-repository threshold separately and can drop a
hostname that meets the threshold only across the complete result. Likewise,
when evaluating cumulative Tier A and B evidence, import their combined seed
so repository counts span both tiers. Retain the originals and the combined
file privately.

## Import and measure yield

With the complete local JSONL file saved as `.private/bigquery/tier-a.jsonl`:

~~~console
python scripts/import_seed.py .private/bigquery/tier-a.jsonl --dry-run
python scripts/import_seed.py .private/bigquery/tier-a.jsonl
python scripts/validate.py
~~~

The first command makes no changes and no network requests. Inspect its
records-read, skipped-record, extracted-observation, and candidates-added counts
before running the second command. The default admission threshold is five
distinct repositories per new seed-only host; do not lower it merely to make a
small sample produce more candidates. Import only adds evidence and candidates;
it does not approve or publish targets.

Review `git diff` for `data/candidates.json` and `reviews/pending/`, then use the
[Codex review handoff](review-workflow.md#codex-review-handoff). Count useful new
hosts, newly supported ecosystems, independent owners, stale evidence, and
irrelevant/private endpoints. A high raw row count alone does not justify a
larger scan. Keep source files in `.private/`; commit only reviewed public
evidence metadata and the generated queue.

## Keep extraction local

The export contract is exactly three fields because `scripts/import_seed.py`
consumes that shape. Each newline is one JSON object, with newlines inside
file content escaped as JSON characters:

~~~json
{"repo_name": "owner/project", "path": "config/pip.conf", "content": "..."}
~~~

The SQL selects files; it does not extract URLs. URL extraction happens locally
after import, where the repository's format-aware extractors read `path` and
`content` and apply the same validation rules as ordinary discovery. Moving
regex URL extraction into BigQuery would be the generic line-wide matching that
`scripts/validate.py` rejects. It would also discard the format-aware
extractor guarantee on which the project relies, so a query that returns
already-matched URLs is not a valid seed.

## Count repositories before admitting a hostname

The minimum distinct-repository count is meaningful only at BigQuery scale. At
GitHub-search scale, the workflow never sees more than about twenty results, so
counting distinct repositories there mostly measures the search cap rather than
the reach of an endpoint. A BigQuery seed can observe a registry across many
thousands of public repositories. A single company's private Artifactory, by
contrast, usually appears only in that company's few open-sourced repositories.

Count distinct `repo_name` values that produce each normalized hostname, not
file rows or repeated matches from one repository, and apply the seed's
minimum repository-count threshold before placing that hostname in the review
queue. This threshold reduces low-reach noise but does not establish independent
ownership or public accessibility. Review also shows distinct owner and content
counts, making one company's many repositories visible as such. The count is an
admission filter, not proof that a hostname is safe or a reason to bypass review.

Each new imported source records the seed file's SHA-256. Retain the original
seed privately for replay; see [evidence continuity](review-workflow.md#evidence-continuity).

## Provenance and trust boundary

Imported candidates carry `source_kind: "bigquery-github"` and retain the seed
file evidence needed to review the repository and path that produced them.
They are review candidates like every other discovery. The seed never promotes
a candidate automatically, and constructed source URLs for repositories and
paths are evidence metadata only; they are never fetched. The BigQuery snapshot
and the public file contents are untrusted input, so normal parsing, filtering,
validation, and human approval still apply after import.

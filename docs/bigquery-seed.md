# BigQuery seed extraction

GitHub code search is the recurring discovery path, but it has a fixed ceiling:
it permits roughly ten requests per minute and returns at most 1000 results for
one query. Adding more query patterns does not create more volume after those
limits are reached. The public GitHub dataset in BigQuery is therefore an
infrequent seed source, not a replacement feed. A person produces the seed out
of band and imports a file; the weekly workflow remains standard-library-only
and needs no Google Cloud credentials.

## Check freshness before scanning content

The `bigquery-public-data.github_repos` dataset was documented in 2017 as
refreshing weekly. That schedule is not verified today, and the available
dataset may be a stale snapshot. Check the table metadata before estimating or
running a content query:

~~~sql
SELECT table_id, TIMESTAMP_MILLIS(last_modified_time) AS last_modified,
       ROUND(size_bytes/POW(1024,4), 2) AS size_tib, row_count
FROM `bigquery-public-data.github_repos.__TABLES__`
ORDER BY table_id
~~~

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
query or incurring a charge. The figure is exact for that query, and the dry
run is free, so it is the authoritative basis for the decision. For a saved
query, the command is:

~~~console
bq query --location=US --use_legacy_sql=false --dry_run < tier-a-select.sql
~~~

Dry-run the bare `SELECT`, not the `EXPORT DATA` wrapper. A dry run reports the
scan estimate for a query; a scripting statement such as `EXPORT DATA` may
return no useful byte figure, which reads as reassuringly small rather than as
unmeasured. Keep a copy of each query with the export wrapper removed for this
purpose.

Start with `github_repos.sample_contents`, which is roughly a ten-percent
sample and fits the free monthly terabyte. Run Tier A there first, then use its
yield to decide whether Tier B is warranted. Only replace
`sample_contents` with the full `contents` table after the sample produces
enough distinct, usable registry evidence to justify the larger scan, and
dry-run that changed query again. A path predicate does not make selecting the
full `content` column cheap.

## Stage the extraction

The two tiers put high-signal evidence ahead of the common files that produce
the largest export. Both queries below export newline-delimited JSON. Replace
the bucket name with a location controlled by the person producing the seed;
the wildcard lets BigQuery write multiple export shards.

### Tier A: rare configuration files

Tier A selects filenames that are uncommon enough to keep the first export
small while still carrying package-manager registry settings: `.npmrc`,
`.yarnrc`, `.yarnrc.yml`, `pip.conf`, `pip.ini`, `.condarc`,
`environment.yml`, `environment.yaml`, `settings.xml`, `NuGet.Config`,
`paket.dependencies`, `Pipfile`, and `bunfig.toml`.

~~~sql
EXPORT DATA OPTIONS (
  uri = 'gs://REPLACE_WITH_YOUR_BUCKET/package-url-seed/tier-a-*.json',
  format = 'JSON',
  overwrite = true
) AS
SELECT
  f.repo_name AS repo_name,
  f.path AS path,
  c.content AS content
FROM `bigquery-public-data.github_repos.files` AS f
JOIN `bigquery-public-data.github_repos.sample_contents` AS c
  ON f.id = c.id
WHERE REGEXP_CONTAINS(
  f.path,
  r'(?i)(^|/)(\.npmrc|\.yarnrc|\.yarnrc\.yml|pip\.conf|pip\.ini|\.condarc|environment\.yml|environment\.yaml|settings\.xml|NuGet\.Config|paket\.dependencies|Pipfile|bunfig\.toml)$'
)
  AND c.binary IS NOT TRUE
~~~

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

~~~sql
EXPORT DATA OPTIONS (
  uri = 'gs://REPLACE_WITH_YOUR_BUCKET/package-url-seed/tier-b-*.json',
  format = 'JSON',
  overwrite = true
) AS
SELECT
  f.repo_name AS repo_name,
  f.path AS path,
  c.content AS content
FROM `bigquery-public-data.github_repos.files` AS f
JOIN `bigquery-public-data.github_repos.sample_contents` AS c
  ON f.id = c.id
WHERE REGEXP_CONTAINS(
  f.path,
  r'(?i)(^|/)(package\.json|pom\.xml|requirements[^/]*\.txt|pyproject\.toml|build\.gradle(?:\.kts)?|[^/]+\.csproj|Directory\.Packages\.props)$'
)
  AND c.binary IS NOT TRUE
~~~

To use the full dataset, change only the `sample_contents` table reference to
`contents` after the dry run and yield review described above. Keeping the
queries otherwise identical makes the sample result a meaningful estimate of
which filenames and ecosystems warrant the full pass.

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
queue. The threshold is the primary safety signal that separates a broadly
used public registry from an organisation's internal endpoint at this scale.
It keeps a large export from flooding review with other organisations'
internal Artifactory and similar endpoints, which is the failure this
repository exists to avoid. The count is an admission filter, not proof that a
hostname is safe or a reason to bypass human review.

## Provenance and trust boundary

Imported candidates carry `source_kind: "bigquery-github"` and retain the seed
file evidence needed to review the repository and path that produced them.
They are review candidates like every other discovery. The seed never promotes
a candidate automatically, and constructed source URLs for repositories and
paths are evidence metadata only; they are never fetched. The BigQuery snapshot
and the public file contents are untrusted input, so normal parsing, filtering,
validation, and human approval still apply after import.

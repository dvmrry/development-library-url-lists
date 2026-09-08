# Review and publication workflow

Start with `reviews/pending/README.md`. It contains a bounded, balanced batch
across ecosystems, up to three evidence links per target, distinct repository
and owner counts, and the full queue. It is generated locally without an LLM
call. Commands in the report are alternatives and their placeholder rationale
must be replaced before execution.

## Review package evidence and blocking scope separately

High confidence means strong evidence of package use. It does not establish
public accessibility or justify blocking a complete shared hostname. Inspect
the source and decide whether the endpoint is a dedicated registry, a shared
mirror, a tenant service, or a shared application with a package-serving path.
The `repository_urls` field retains normalized host/path observations on new
discoveries. It contains no credentials, query strings, or fragments. Older
evidence may lack this field; check its linked configuration.

Count independent owners as well as repositories. Five repositories from one
company are different from five unrelated users; neither count proves public
availability. Fork relationships are not currently verified. Published catalog
identities do not count as independent GitHub repositories.

## Record the decision

```sh
python scripts/promote.py packages.vendor.net --category python --review-note 'Official public index; dedicated package hostname'
```

To add a newly evidenced ecosystem to an existing exact entry:

```sh
python scripts/promote.py packages.vendor.net --extend --category javascript --review-note 'Official npm endpoint on the existing registry host'
```

This preserves existing categories, kind, and evidence. Other pending category
suggestions remain queued. An entry covered only by a provider suffix receives
a new exact entry for the additional ecosystem instead of broadening the
provider-wide suffix. Nothing is promoted automatically.

For an unsuitable candidate:

```sh
python scripts/reject.py packages.vendor.net --reason 'Company-only artifact service; unsuitable for the public reference list'
```

All decisions refresh `dist/` and `reviews/pending/`. A review note, when
provided, is retained with the date and selected categories in the catalog.
Review notes must not contain confidential information.

## Evidence continuity

Changes to discovery rules retain old candidates with per-source
`needs_revalidation` flags. Flagged sources cannot raise confidence. A new
observation or replay of an offline seed clears the flag only for the source
actually reprocessed. Human promotion while any source remains flagged requires
an explicit review note. Rejection and exclusion rules still apply immediately.

The automation branch's evidence is merged with the checked-out snapshot;
it does not replace newly committed offline imports. Matching source identities
prefer the checked-out record; additional sources from the automation snapshot
are retained. Sources from a different rules fingerprint need revalidation.

Retain original offline seed files privately. New imported sources carry a
SHA-256 of the input file (compressed bytes for gzip inputs), alongside their
per-configuration content hash. Verify that hash before replaying the import
with the same repository threshold. BigQuery source links use `blob/HEAD` and
may drift from the original snapshot; the retained seed and hashes supply the
replay evidence. Raw seed contents are never published by the importer.

Discovery prints a run summary and appends it to GitHub's Actions summary. A
local copy is kept at `.private/discovery-run.json`. Partial runs preserve
evidence from unavailable sources; a total source outage leaves the candidate
file unchanged and fails the run.

If a rate-limited host exhausts retries or asks for more waiting time than the
remaining budget permits, subsequent requests to that host are deferred for the
rest of that collector pass. Other source hosts can still complete. This avoids
immediately sending the next query against the same exhausted service quota.

## Compare with observed traffic offline

Supply a sanitized JSONL sample. Each line is a JSON string containing a URL,
or an object with `url` and an optional positive integer `requests`:

```json
{"url":"https://pypi.org/simple/requests/","requests":12}
{"url":"https://unlisted.vendor.net/packages/","requests":3}
```

```sh
python scripts/audit_traffic.py /path/to/sanitized-traffic.jsonl
```

The report defaults to `.private/traffic-review.json`. It groups normalized
targets, counts covered and uncovered requests, lists matching catalog entries,
and highlights matches that rely solely on host/suffix scope. URL credentials
are rejected and query strings are discarded. Paths can still be sensitive:
sanitize the sample and keep the report private. This command makes no network
requests and does not change the catalog.

This is reference-list matching, not a simulation of Zscaler rule precedence,
TLS inspection, wildcard limits, or tenant exceptions. Uncovered URLs are leads
for investigation, not proof of missing package repositories. Validate matching
behavior and upstream access with actual build traffic before enforcement.

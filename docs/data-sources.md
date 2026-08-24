# Published discovery and enrichment sources

The workflow treats every external response as untrusted input. Source URLs are
fixed in code, response sizes are bounded, redirects are revalidated, and hosts
found inside a list are normalized but never fetched. All discoveries remain
review candidates.

## Deterministic discovery

| Source | Machine-readable endpoint | Candidate use | Admission filter |
| --- | --- | --- | --- |
| ecosyste.ms Packages | <https://packages.ecosyste.ms/api/v1/registries> | Cross-ecosystem registry catalog | Known Package-URL/ecosystem mapping and valid HTTP(S) registry URL |
| MirrorZ / CERNET | <https://mirrors.cernet.edu.cn/api/scoring> | Regional and university multi-ecosystem mirrors | Valid public resolver hostname |
| CRAN | <https://cran.r-project.org/CRAN_mirrors.csv> | R package mirrors | `OK` equals `1` |
| Alpine Linux | <https://mirrors.alpinelinux.org/mirrors.txt> | Operating-system package mirrors | Valid HTTP(S) entry |
| Arch Linux | <https://archlinux.org/mirrors/status/json/> | Operating-system package mirrors | Active HTTP(S), at least 90% complete, and a current score |
| Debian | <https://mirror-master.debian.org/status/Mirrors.masterlist> | Operating-system package mirrors | Site advertises an HTTP or HTTPS archive endpoint |

Official distribution lists are high-confidence evidence that a host is an
active package mirror. ecosyste.ms and MirrorZ are third-party catalogs and are
medium-confidence evidence. Confidence accelerates review; it does not promote
an entry automatically.

Each feed has a conservative minimum expected record count. A successful
refresh removes mirrors no longer present, but a failed, malformed, or
implausibly small response retains the prior evidence and raises a workflow
warning. Stable per-record fingerprints prevent volatile health counters from
rewriting every candidate on every run.

ecosyste.ms publishes its data under
[CC BY-SA 4.0](https://ecosyste.ms/api). Candidate provenance retains the source
endpoint and a stable admitted-record fingerprint for attribution and audit.
Mirror and registry facts obtained from other sources retain any applicable
upstream terms. This repository does not republish source descriptions,
maintainer details, or complete upstream records—only normalized targets and
audit provenance needed for review.

## Cloudflare Domain Intelligence

The private enrichment helper uses Cloudflare's
[bulk Domain Intelligence endpoint](https://developers.cloudflare.com/api/resources/intel/subresources/domains/subresources/bulks/methods/get/).
The token needs only `Account > Intel > Read` and should be scoped to one
account. Use `CLOUDFLARE_API_TOKEN` as a secret and `CLOUDFLARE_ACCOUNT_ID` as
a variable on the private runner.

The public repository does not persist or display Cloudflare responses.
Cloudflare's Cloudforce One
[service-specific terms](https://www.cloudflare.com/service-specific-terms-other-terms/)
limit third-party disclosure of API-delivered threat intelligence, while public
redistribution rights for the ordinary Domain Intelligence response are not
explicit. Public automation therefore exports only the original candidate
queue. `scripts/enrich_cloudflare.py` writes detailed results beneath the
gitignored `.private/` directory for internal review.

Cloudflare currently documents
[100 calls per month](https://developers.cloudflare.com/security-center/intel-apis/limits/)
for Free, Pro, and Business accounts. The private helper therefore:

- batches at most 20 domains per request;
- makes at most 20 calls per scheduled run;
- leaves optional ranking disabled;
- queries only missing or 90-day-stale candidates; and
- writes each successful batch to the cache before attempting the next one.

Cloudflare classifications are not assumed to match Zscaler categories. They
are independent evidence to help prioritize and identify suspicious or clearly
irrelevant candidates before the final Zscaler Site Review pass on a
Zscaler-connected device.

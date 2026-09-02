# Security Policy

This repository publishes reference data, not a guarantee that any listed
service is malicious or compromised. Consumers must review policy impact
before enforcement.

Please report vulnerabilities privately through GitHub's security-advisory
interface when available.

The discovery workflow deliberately does not fetch newly discovered URLs.
Collectors are restricted to a fixed allowlist of GitHub, package-catalog, and
official distribution hosts so that malicious public configuration files or
catalog records cannot turn the workflow into an SSRF client. Redirects are
revalidated against the same allowlist.

The public scheduled workflow does not receive the Cloudflare API token or
publish Cloudflare intelligence. The private/local helper can contact only
`api.cloudflare.com`, refuses redirects, validates the account ID and every
domain, bounds response size, and never prints the token. Responses are treated
as untrusted input: their schema and documented ranges are checked before output
is written beneath the gitignored `.private/` directory.

The optional LLM reviewer follows the same trust boundary. It sends a bounded
inventory, without raw discovered file contents, to one fixed provider endpoint.
Only the selected workflow step receives that provider's API key. Model output
is treated as untrusted: it is schema-checked, normalized, size-limited, marked
suggestion-only, and cannot edit the catalog or generated lists. Model-proposed
evidence links are stored for human inspection but are never fetched by the
workflow.

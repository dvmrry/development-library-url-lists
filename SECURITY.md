# Security Policy

This repository publishes reference data, not a guarantee that any listed
service is malicious or compromised. Consumers must review policy impact
before enforcement.

Please report vulnerabilities privately through GitHub's security-advisory
interface when available.

The discovery workflow deliberately does not fetch newly discovered URLs.
Collectors are restricted to fixed GitHub-owned API hosts so that malicious
public configuration files cannot turn the workflow into an SSRF client.

The optional LLM reviewer follows the same trust boundary. It sends a bounded
inventory, without raw discovered file contents, to one fixed provider endpoint.
Only the selected workflow step receives that provider's API key. Model output
is treated as untrusted: it is schema-checked, normalized, size-limited, marked
suggestion-only, and cannot edit the catalog or generated lists. Model-proposed
evidence links are stored for human inspection but are never fetched by the
workflow.

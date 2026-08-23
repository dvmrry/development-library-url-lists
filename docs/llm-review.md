# Optional LLM coverage review

The scheduled discovery job can run one hosted model after deterministic
collection and before it opens or updates the candidate pull request. The model
produces a review report; it cannot promote targets, edit generated URL lists,
fetch a proposed URL, or change external policy.

~~~text
fixed-source collectors -> compact inventory -> one LLM request
                                            -> strict local validation
                                            -> reviews/llm/latest.{json,md}
                                            -> human review and promotion
~~~

The feature is disabled by default. With no provider configured, the project
keeps its existing zero-paid-service behavior.

## Why pre-PR

The review runs against the newly discovered candidate queue and lands in the
same automation PR. This makes its exact input hash, provider, model, token
usage, suggestions, and proposed evidence visible before anything is accepted.
It also avoids giving a general-purpose agent a GitHub write token.

A post-PR agent can still be useful as a second opinion. For example, Claude
Code Routines can run from a Pro, Max, Team, or Enterprise subscription and can
trigger on schedules or GitHub events. That path connects a personal or work
account and can act through its linked GitHub identity, so it should be treated
as a separate reviewer rather than the list-generation mechanism.

## Provider choices

The adapters use fixed provider endpoints and Python's standard library. Prices
and product availability change; the links below are the source of truth.

| Provider | Default model | Account/cost shape | Practical fit |
| --- | --- | --- | --- |
| OpenAI | `gpt-5.4-mini` | Separate API key and usage billing. At current list prices, the expected weekly request is pennies. | Recommended paid baseline for stronger gap analysis and strict structured output. |
| Anthropic | `claude-haiku-4-5` | Separate API key for this GitHub Actions adapter. Claude subscription Routines are an alternative outside the workflow. | Useful when Claude is already approved by the organization. |
| Gemini | `gemini-3.5-flash-lite` | A limited API free tier is available. Google states that free-tier content may be used to improve its products; paid-tier content is not. | Best zero-incremental-cost experiment for this public-data repository. |
| DeepSeek | `deepseek-v4-flash` | Separate prepaid API account; JSON mode rather than schema-constrained output. | Low-cost experiment when organizational data-processing and provider approval permit it. |

Current references:

- [OpenAI GPT-5.4 mini](https://developers.openai.com/api/docs/models/gpt-5.4-mini)
- [Anthropic Claude Haiku](https://www.anthropic.com/claude/haiku)
- [Claude Code Routines](https://code.claude.com/docs/en/routines)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [DeepSeek models and pricing](https://api-docs.deepseek.com/quick_start/pricing)

GitHub Models is not an option for this spike. GitHub fully retired that
service on July 30, 2026; see the current [GitHub Models notice](https://docs.github.com/en/github-models).

## Enable one provider

In the repository's **Settings > Secrets and variables > Actions**:

1. Add a repository variable named `LLM_REVIEW_PROVIDER` with one lowercase
   value: `openai`, `anthropic`, `gemini`, or `deepseek`.
2. Add only the matching repository secret:

   | Provider | Secret |
   | --- | --- |
   | OpenAI | `OPENAI_API_KEY` |
   | Anthropic | `ANTHROPIC_API_KEY` |
   | Gemini | `GEMINI_API_KEY` |
   | DeepSeek | `DEEPSEEK_API_KEY` |

3. Optionally add `LLM_REVIEW_MODEL` as a repository variable to override the
   default model.
4. Run **Discover package repositories** manually, or wait for its weekly run.

Only the selected provider step receives its API secret. A missing key, API
failure, refusal, malformed response, or failed local validation produces a
workflow warning but does not stop deterministic discovery.

For a local run:

~~~powershell
$env:LLM_REVIEW_PROVIDER = "openai"
$env:OPENAI_API_KEY = "..."
python scripts/llm_review.py
~~~

Do not commit an API key or place it in a model, endpoint, or repository
variable.

## Review contract

The provider receives a bounded JSON inventory containing categories, curated
targets, candidate targets, rejection summaries, discovery queries, and at most
three evidence links per entry. It does not receive raw public configuration
file contents.

The resulting report is deliberately constrained:

- at most 25 findings and eight targets per finding;
- only known category identifiers, plus normalized proposed identifiers for a
  genuinely missing language, runtime, or package-manager category;
- normalized public hostnames or suffixes;
- one to eight public HTTPS evidence links per finding;
- stable finding IDs and deterministic flags for targets already approved,
  queued, or rejected;
- provider, model, prompt version, input SHA-256, timestamp, and token usage;
- `suggestion-only` and `unverified` labels in both JSON and Markdown.

Model-proposed evidence is not automatically fetched. This prevents a suggested
link from becoming an SSRF or metadata-service request and avoids falsely
treating a plausible-looking URL as proof. A person must inspect the link,
confirm the endpoint and category, and then use the normal promotion command.

## Follow-on spike

If the model reviews are useful, evidence verification should be a separate,
deterministic stage with DNS/IP checks, redirect revalidation, fixed response
limits, and an explicit allowlist of documentation hosts. That verifier should
annotate a suggestion; it still should not promote or remove a URL-category
target automatically.

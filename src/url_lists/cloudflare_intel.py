"""Quota-conscious Cloudflare Domain Intelligence enrichment."""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .catalog import CatalogError, read_json, write_json_atomic
from .normalize import TargetError, normalize_target, target_hostname


CLOUDFLARE_API_ROOT = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_CACHE = Path(".private/cloudflare/cache.json")
CLOUDFLARE_REVIEW_JSON = Path(".private/cloudflare/latest.json")
CLOUDFLARE_REVIEW_MARKDOWN = Path(".private/cloudflare/latest.md")
MAX_BATCH_SIZE = 20
MAX_RESPONSE_BYTES = 2_000_000
DEFAULT_MAX_CALLS = 20
DEFAULT_STALE_DAYS = 90


class CloudflareIntelError(RuntimeError):
    """Raised when Cloudflare enrichment cannot safely continue."""


class _NoRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        raise CloudflareIntelError("Cloudflare API unexpectedly redirected the request")


_OPENER = build_opener(_NoRedirectHandler())


def _validate_account_id(account_id: str) -> str:
    value = account_id.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{32}", value):
        raise CloudflareIntelError("CLOUDFLARE_ACCOUNT_ID must be a 32-character ID")
    return value.lower()


def _validate_domain(domain: str) -> str:
    try:
        normalized = normalize_target(domain, preserve_path=False)
    except TargetError as error:
        raise CloudflareIntelError(f"invalid Cloudflare lookup domain: {domain!r}") from error
    if normalized != domain or ":" in normalized:
        raise CloudflareIntelError(f"Cloudflare lookup requires a bare domain: {domain!r}")
    return normalized


def _response_error_message(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "Cloudflare returned an invalid error response"
    messages = []
    for item in payload.get("errors", []):
        if not isinstance(item, dict):
            continue
        code = item.get("code")
        message = item.get("message")
        if isinstance(message, str) and message:
            messages.append(f"{code}: {message}" if isinstance(code, int) else message)
    return "; ".join(messages)[:500] or "Cloudflare rejected the request"


def _named_items(value: Any, field: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CloudflareIntelError(f"Cloudflare {field} field changed shape")
    normalized = []
    for item in value:
        if not isinstance(item, dict):
            raise CloudflareIntelError(f"Cloudflare {field} entry changed shape")
        identifier = item.get("id")
        name = item.get("name")
        super_category_id = item.get("super_category_id")
        if identifier is not None and not isinstance(identifier, int):
            raise CloudflareIntelError(f"Cloudflare {field} ID changed shape")
        if name is not None and not isinstance(name, str):
            raise CloudflareIntelError(f"Cloudflare {field} name changed shape")
        if identifier is None and name is None:
            raise CloudflareIntelError(f"Cloudflare {field} entry is empty")
        result: dict[str, Any] = {}
        if identifier is not None:
            result["id"] = identifier
        if name is not None:
            result["name"] = name
        if super_category_id is not None:
            if not isinstance(super_category_id, int):
                raise CloudflareIntelError(
                    f"Cloudflare {field} super-category changed shape"
                )
            result["super_category_id"] = super_category_id
        normalized.append(result)
    return sorted(
        normalized,
        key=lambda item: (
            str(item.get("name", "")).lower(),
            int(item.get("id", -1)),
        ),
    )


def _application(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise CloudflareIntelError("Cloudflare application field changed shape")
    identifier = value.get("id")
    name = value.get("name")
    if identifier is not None and not isinstance(identifier, int):
        raise CloudflareIntelError("Cloudflare application ID changed shape")
    if name is not None and not isinstance(name, str):
        raise CloudflareIntelError("Cloudflare application name changed shape")
    if identifier is None and name is None:
        raise CloudflareIntelError("Cloudflare application field is empty")
    result = {}
    if identifier is not None:
        result["id"] = identifier
    if name is not None:
        result["name"] = name
    return result


def _normalize_result(item: Any) -> tuple[str, dict[str, Any]]:
    if not isinstance(item, dict) or not isinstance(item.get("domain"), str):
        raise CloudflareIntelError("Cloudflare domain result changed shape")
    domain = _validate_domain(item["domain"].lower())
    risk_score = item.get("risk_score")
    if risk_score is not None and (
        not isinstance(risk_score, (int, float))
        or isinstance(risk_score, bool)
        or not 0 <= risk_score <= 1
    ):
        raise CloudflareIntelError("Cloudflare risk score is outside the documented range")
    inherited_from = item.get("inherited_from")
    if inherited_from is not None and not isinstance(inherited_from, str):
        raise CloudflareIntelError("Cloudflare inherited_from field changed shape")
    additional_information = item.get("additional_information")
    suspected_family = None
    if additional_information is not None:
        if not isinstance(additional_information, dict):
            raise CloudflareIntelError(
                "Cloudflare additional_information field changed shape"
            )
        candidate_family = additional_information.get("suspected_malware_family")
        if candidate_family is not None and not isinstance(candidate_family, str):
            raise CloudflareIntelError("Cloudflare malware family field changed shape")
        suspected_family = candidate_family or None

    normalized = {
        "application": _application(item.get("application")),
        "content_categories": _named_items(
            item.get("content_categories"),
            "content_categories",
        ),
        "inherited_content_categories": _named_items(
            item.get("inherited_content_categories"),
            "inherited_content_categories",
        ),
        "inherited_from": inherited_from,
        "inherited_risk_types": _named_items(
            item.get("inherited_risk_types"),
            "inherited_risk_types",
        ),
        "risk_score": risk_score,
        "risk_types": _named_items(item.get("risk_types"), "risk_types"),
        "suspected_malware_family": suspected_family,
    }
    return domain, normalized


def fetch_domain_batch(
    account_id: str,
    token: str,
    domains: Iterable[str],
) -> dict[str, dict[str, Any]]:
    """Fetch and strictly normalize one Cloudflare bulk domain response."""

    safe_account_id = _validate_account_id(account_id)
    domain_list = [_validate_domain(domain) for domain in domains]
    if not 1 <= len(domain_list) <= MAX_BATCH_SIZE:
        raise CloudflareIntelError(
            f"Cloudflare bulk requests require 1-{MAX_BATCH_SIZE} domains"
        )
    if len(domain_list) != len(set(domain_list)):
        raise CloudflareIntelError("Cloudflare bulk request contains duplicate domains")
    if not token:
        raise CloudflareIntelError("CLOUDFLARE_API_TOKEN is empty")

    query = urlencode(
        [("domain", domain) for domain in domain_list]
        + [("include_ranking", "false")]
    )
    url = (
        f"{CLOUDFLARE_API_ROOT}/accounts/{safe_account_id}/intel/domain/bulk?{query}"
    )
    request = Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "development-library-url-lists/0.1",
        },
    )
    try:
        with _OPENER.open(request, timeout=30) as response:
            content = response.read(MAX_RESPONSE_BYTES + 1)
    except HTTPError as error:
        try:
            payload = json.loads(error.read(65_537))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = None
        raise CloudflareIntelError(
            f"Cloudflare API HTTP {error.code}: {_response_error_message(payload)}"
        ) from error
    except (URLError, TimeoutError, UnicodeError) as error:
        raise CloudflareIntelError(
            f"Cloudflare API request failed: {type(error).__name__}"
        ) from error
    if len(content) > MAX_RESPONSE_BYTES:
        raise CloudflareIntelError("Cloudflare API response exceeded the safety limit")
    try:
        payload = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise CloudflareIntelError("Cloudflare API returned invalid JSON") from error
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise CloudflareIntelError(_response_error_message(payload))
    results = payload.get("result")
    if not isinstance(results, list):
        raise CloudflareIntelError("Cloudflare API result changed shape")
    normalized = dict(_normalize_result(item) for item in results)
    missing = sorted(set(domain_list) - set(normalized))
    unexpected = sorted(set(normalized) - set(domain_list))
    if missing or unexpected:
        raise CloudflareIntelError(
            "Cloudflare bulk response did not match the requested domain set"
        )
    return normalized


def empty_cache() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "provider": "cloudflare-domain-intelligence",
        "entries": {},
    }


def validate_cache(document: Any) -> list[str]:
    if not isinstance(document, dict):
        return ["Cloudflare cache must be an object"]
    if document.get("schema_version") != 1:
        return ["unsupported Cloudflare cache schema version"]
    if document.get("provider") != "cloudflare-domain-intelligence":
        return ["Cloudflare cache provider is invalid"]
    entries = document.get("entries")
    if not isinstance(entries, dict):
        return ["Cloudflare cache entries must be an object"]
    problems = []
    for domain, entry in entries.items():
        label = f"Cloudflare cache entry {domain!r}"
        try:
            if _validate_domain(domain) != domain:
                problems.append(f"{label} is not normalized")
        except CloudflareIntelError as error:
            problems.append(f"{label} is invalid: {error}")
            continue
        if not isinstance(entry, dict):
            problems.append(f"{label} must be an object")
            continue
        checked_on = entry.get("checked_on")
        try:
            date.fromisoformat(checked_on)
        except (TypeError, ValueError):
            problems.append(f"{label} has an invalid checked_on date")
        try:
            _application(entry.get("application"))
            _named_items(entry.get("content_categories"), "content_categories")
            _named_items(
                entry.get("inherited_content_categories"),
                "inherited_content_categories",
            )
            _named_items(entry.get("inherited_risk_types"), "inherited_risk_types")
            _named_items(entry.get("risk_types"), "risk_types")
        except CloudflareIntelError as error:
            problems.append(f"{label} is invalid: {error}")
        risk_score = entry.get("risk_score")
        if risk_score is not None and (
            not isinstance(risk_score, (int, float))
            or isinstance(risk_score, bool)
            or not 0 <= risk_score <= 1
        ):
            problems.append(f"{label} has an invalid risk score")
        inherited_from = entry.get("inherited_from")
        if inherited_from is not None and not isinstance(inherited_from, str):
            problems.append(f"{label} has an invalid inherited_from value")
        family = entry.get("suspected_malware_family")
        if family is not None and not isinstance(family, str):
            problems.append(f"{label} has an invalid malware family")
    return problems


def load_cache(root: Path) -> dict[str, Any]:
    path = root / CLOUDFLARE_CACHE
    if not path.exists():
        return empty_cache()
    try:
        document = read_json(path)
    except CatalogError as error:
        raise CloudflareIntelError(str(error)) from error
    problems = validate_cache(document)
    if problems:
        raise CloudflareIntelError(problems[0])
    return document


def _candidate_targets(root: Path) -> tuple[list[str], dict[str, str]]:
    try:
        document = read_json(root / "data" / "candidates.json")
    except CatalogError as error:
        raise CloudflareIntelError(str(error)) from error
    candidates = document.get("candidates") if isinstance(document, dict) else None
    if not isinstance(candidates, list):
        raise CloudflareIntelError("candidate document has an unexpected shape")
    priorities: dict[str, str] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            domain = target_hostname(candidate["target"])
        except (KeyError, TargetError):
            continue
        confidence = candidate.get("confidence")
        if confidence not in {"high", "medium", "low"}:
            confidence = "low"
        current = priorities.get(domain)
        rank = {"high": 0, "medium": 1, "low": 2}
        if current is None or rank[confidence] < rank[current]:
            priorities[domain] = confidence
    ordered = sorted(
        priorities,
        key=lambda domain: (
            {"high": 0, "medium": 1, "low": 2}[priorities[domain]],
            domain,
        ),
    )
    return ordered, priorities


def _is_stale(entry: Any, *, today: date, stale_days: int) -> bool:
    if not isinstance(entry, dict):
        return True
    try:
        checked_on = date.fromisoformat(entry["checked_on"])
    except (KeyError, TypeError, ValueError):
        return True
    return checked_on <= today - timedelta(days=stale_days)


def enrich_candidates(
    root: Path,
    *,
    account_id: str,
    token: str,
    max_calls: int = DEFAULT_MAX_CALLS,
    stale_days: int = DEFAULT_STALE_DAYS,
    today: date | None = None,
    fetcher: Callable[[str, str, Iterable[str]], dict[str, dict[str, Any]]] = (
        fetch_domain_batch
    ),
) -> dict[str, Any]:
    """Enrich only missing/stale candidates and persist each successful batch."""

    _validate_account_id(account_id)
    if not token:
        raise CloudflareIntelError("CLOUDFLARE_API_TOKEN is empty")
    if not 1 <= max_calls <= 100:
        raise CloudflareIntelError("max_calls must be between 1 and 100")
    if stale_days < 1:
        raise CloudflareIntelError("stale_days must be positive")

    run_date = today or date.today()
    cache = load_cache(root)
    entries = cache["entries"]
    targets, _ = _candidate_targets(root)
    pending = [
        domain
        for domain in targets
        if _is_stale(entries.get(domain), today=run_date, stale_days=stale_days)
    ]
    selected = pending[: max_calls * MAX_BATCH_SIZE]
    refreshed: list[str] = []
    calls_made = 0
    provider_error = None
    for offset in range(0, len(selected), MAX_BATCH_SIZE):
        batch = selected[offset : offset + MAX_BATCH_SIZE]
        calls_made += 1
        try:
            results = fetcher(account_id, token, batch)
        except CloudflareIntelError as error:
            provider_error = str(error)[:500]
            break
        for domain in batch:
            entry = dict(results[domain])
            entry["checked_on"] = run_date.isoformat()
            entries[domain] = entry
            refreshed.append(domain)
        write_json_atomic(root / CLOUDFLARE_CACHE, cache)

    remaining = len(pending) - len(refreshed)
    if provider_error and not refreshed:
        status = "error"
    elif provider_error or remaining:
        status = "partial"
    elif refreshed:
        status = "ok"
    else:
        status = "current"
    relevant_dates = [
        entry.get("checked_on")
        for domain, entry in entries.items()
        if domain in set(targets) and isinstance(entry, dict)
    ]
    relevant_dates = [value for value in relevant_dates if isinstance(value, str)]
    return {
        "schema_version": 1,
        "provider": "cloudflare-domain-intelligence",
        "status": status,
        "as_of": run_date.isoformat() if calls_made or provider_error else max(relevant_dates, default=None),
        "candidate_domain_count": len(targets),
        "cached_domain_count": sum(domain in entries for domain in targets),
        "refreshed_domain_count": len(refreshed),
        "remaining_domain_count": remaining,
        "calls_made": calls_made,
        "provider_error": provider_error,
        "refreshed_domains": refreshed,
    }


def skipped_report(root: Path, message: str) -> dict[str, Any]:
    targets, _ = _candidate_targets(root)
    cache = load_cache(root)
    return {
        "schema_version": 1,
        "provider": "cloudflare-domain-intelligence",
        "status": "skipped",
        "as_of": None,
        "candidate_domain_count": len(targets),
        "cached_domain_count": sum(domain in cache["entries"] for domain in targets),
        "refreshed_domain_count": 0,
        "remaining_domain_count": len(
            [domain for domain in targets if domain not in cache["entries"]]
        ),
        "calls_made": 0,
        "provider_error": message[:500],
        "refreshed_domains": [],
    }


def validate_review_files(root: Path) -> list[str]:
    json_path = root / CLOUDFLARE_REVIEW_JSON
    markdown_path = root / CLOUDFLARE_REVIEW_MARKDOWN
    if not json_path.exists() and not markdown_path.exists():
        return []
    if not json_path.exists() or not markdown_path.exists():
        return ["Cloudflare review JSON and Markdown must either both exist or both be absent"]
    try:
        report = read_json(json_path)
    except CatalogError as error:
        return [str(error)]
    if not isinstance(report, dict) or report.get("schema_version") != 1:
        return ["Cloudflare review has an unsupported schema"]
    problems = []
    if report.get("provider") != "cloudflare-domain-intelligence":
        problems.append("Cloudflare review provider is invalid")
    if report.get("status") not in {"current", "error", "ok", "partial", "skipped"}:
        problems.append("Cloudflare review status is invalid")
    for field in (
        "candidate_domain_count",
        "cached_domain_count",
        "refreshed_domain_count",
        "remaining_domain_count",
        "calls_made",
    ):
        value = report.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            problems.append(f"Cloudflare review {field} is invalid")
    refreshed = report.get("refreshed_domains")
    if not isinstance(refreshed, list) or not all(
        isinstance(domain, str) for domain in refreshed
    ):
        problems.append("Cloudflare review refreshed domains are invalid")
    else:
        for domain in refreshed:
            try:
                _validate_domain(domain)
            except CloudflareIntelError:
                problems.append("Cloudflare review contains an invalid refreshed domain")
                break
    provider_error = report.get("provider_error")
    if provider_error is not None and not isinstance(provider_error, str):
        problems.append("Cloudflare review provider error is invalid")
    as_of = report.get("as_of")
    if as_of is not None:
        try:
            date.fromisoformat(as_of)
        except (TypeError, ValueError):
            problems.append("Cloudflare review as_of date is invalid")
    try:
        markdown_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        problems.append("Cloudflare review Markdown is not readable UTF-8")
    return problems


def _display_names(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    return ", ".join(
        str(item["name"]).replace("|", "\\|")
        for item in items
        if isinstance(item, dict) and "name" in item
    )


def write_review(root: Path, report: dict[str, Any]) -> None:
    """Write deterministic machine-readable and human-readable review status."""

    write_json_atomic(root / CLOUDFLARE_REVIEW_JSON, report)
    cache = load_cache(root)
    lines = [
        "# Cloudflare Domain Intelligence enrichment",
        "",
        f"**Status:** `{report['status']}`",
        "",
        f"- Candidate domains: {report['candidate_domain_count']}",
        f"- Cached classifications: {report['cached_domain_count']}",
        f"- Refreshed this run: {report['refreshed_domain_count']}",
        f"- Still pending: {report['remaining_domain_count']}",
        f"- API calls attempted this run: {report['calls_made']}",
    ]
    if report.get("as_of"):
        lines.append(f"- Report as of: {report['as_of']}")
    if report.get("provider_error"):
        lines.extend(["", f"> Provider status: {report['provider_error']}"])
    refreshed = report.get("refreshed_domains", [])
    if refreshed:
        lines.extend(
            [
                "",
                "## Classifications refreshed this run",
                "",
                "| Domain | Application | Content categories | Risk score | Risk types |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        for domain in refreshed[:200]:
            entry = cache["entries"][domain]
            application = entry.get("application")
            application_name = (
                application.get("name") if isinstance(application, dict) else ""
            )
            risk_score = entry.get("risk_score")
            fields = (
                domain.replace("|", "\\|"),
                str(application_name or "").replace("|", "\\|"),
                _display_names(entry.get("content_categories")),
                "" if risk_score is None else str(risk_score),
                _display_names(entry.get("risk_types")),
            )
            lines.append(
                "| " + " | ".join(fields) + " |"
            )
        if len(refreshed) > 200:
            lines.extend(
                [
                    "",
                    f"The table is capped at 200 of {len(refreshed)} refreshed domains; "
                    "the complete normalized results are in the private Cloudflare cache.",
                ]
            )
    lines.extend(
        [
            "",
            "Cloudflare data is review evidence only. It never promotes, rejects, or "
            "changes a URL-category target.",
            "",
        ]
    )
    path = root / CLOUDFLARE_REVIEW_MARKDOWN
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(lines)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8", newline="\n")

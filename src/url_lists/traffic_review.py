"""Offline comparison of observed URLs against the reference catalog."""

from collections import Counter
from typing import Any, Iterable

from .discovery import _is_covered
from .normalize import normalize_target, target_hostname


def review_traffic(records: Iterable[Any], catalog: dict[str, Any]) -> dict[str, Any]:
    observations: Counter[str] = Counter()
    invalid = 0
    for record in records:
        value = record.get("url") if isinstance(record, dict) else record
        requests = record.get("requests", 1) if isinstance(record, dict) else 1
        try:
            if not isinstance(value, str) or type(requests) is not int or requests < 1:
                raise ValueError("invalid traffic row")
            target = normalize_target(value)
            if target.startswith("."):
                raise ValueError("an observation cannot be a suffix rule")
        except ValueError:
            invalid += 1
            continue
        observations[target] += requests

    results = []
    for target, requests in observations.most_common():
        matches = [
            entry for entry in catalog["entries"] if _is_covered(target, [entry])
        ]
        results.append(
            {
                "target": target,
                "domain": target_hostname(target),
                "requests": requests,
                "status": "covered" if matches else "uncovered",
                "matches": [
                    {
                        "target": e["target"],
                        "match": e["match"],
                        "categories": e["categories"],
                    }
                    for e in matches
                ],
                "scope_review": bool(
                    matches and all(e["match"] != "path" for e in matches)
                ),
            }
        )
    return {
        "schema_version": 1,
        "purpose": "offline reference-list comparison; not a simulation of tenant policy or proof that an uncovered URL serves packages",
        "invalid_records": invalid,
        "request_count": sum(observations.values()),
        "covered_requests": sum(
            r["requests"] for r in results if r["status"] == "covered"
        ),
        "uncovered_requests": sum(
            r["requests"] for r in results if r["status"] == "uncovered"
        ),
        "entries": results,
    }

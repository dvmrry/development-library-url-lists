"""Extraction and normalization for URL-category targets."""

from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlsplit


class TargetError(ValueError):
    """Raised when a value cannot safely become a URL-category target."""


URL_RE = re.compile(
    r"https?://[^\s\"'<>()[\]{}\x60]+",
    flags=re.IGNORECASE,
)
TRAILING_PUNCTUATION = ".,;:!?)]}'\""


def extract_urls(text: str) -> list[str]:
    """Return HTTP(S) URLs found in configuration or documentation text."""

    found: list[str] = []
    for match in URL_RE.finditer(text):
        value = match.group(0).rstrip(TRAILING_PUNCTUATION)
        if value:
            found.append(value)
    return found


def _normalize_hostname(hostname: str) -> str:
    hostname = hostname.rstrip(".").lower()
    if not hostname:
        raise TargetError("hostname is empty")

    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise TargetError("hostname is not valid IDNA") from error

    if len(hostname) > 253:
        raise TargetError("hostname is too long")

    labels = hostname.split(".")
    if len(labels) < 2:
        raise TargetError("hostname must contain a public suffix")
    for label in labels:
        if (
            not label
            or len(label) > 63
            or label.startswith("-")
            or label.endswith("-")
            or not re.fullmatch(r"[a-z0-9-]+", label)
        ):
            raise TargetError(f"invalid hostname label: {label!r}")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if not address.is_global:
            raise TargetError("non-global IP addresses are not allowed")

    return hostname


def normalize_target(value: str, *, preserve_path: bool = True) -> str:
    """Normalize a URL, host, or leading-dot suffix into a list target."""

    value = value.strip()
    if not value:
        raise TargetError("target is empty")
    if "*" in value:
        raise TargetError("asterisk wildcards are not allowed")

    suffix = value.startswith(".") and "://" not in value
    parse_value = value[1:] if suffix else value
    parsed = urlsplit(parse_value if "://" in parse_value else f"//{parse_value}")

    if parsed.scheme and parsed.scheme.lower() not in {"http", "https"}:
        raise TargetError("only HTTP and HTTPS targets are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise TargetError("credentials are not allowed")
    if parsed.hostname is None:
        raise TargetError("hostname is missing")

    hostname = _normalize_hostname(parsed.hostname)
    try:
        port = parsed.port
    except ValueError as error:
        raise TargetError("port is invalid") from error

    if suffix and (port is not None or parsed.path not in {"", "/"}):
        raise TargetError("suffix targets cannot contain a port or path")

    authority = hostname
    scheme = parsed.scheme.lower()
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        authority = f"{hostname}:{port}"

    path = ""
    if preserve_path and not suffix:
        raw_path = re.sub(r"/+", "/", parsed.path)
        segments = [part for part in raw_path.split("/") if part]
        if any(part in {".", ".."} for part in segments):
            raise TargetError("dot path segments are not allowed")
        if segments:
            path = "/" + "/".join(segments)

    return f".{hostname}" if suffix else authority + path


def target_hostname(target: str) -> str:
    """Extract the hostname from an already-normalized target."""

    bare = target[1:] if target.startswith(".") else target
    parsed = urlsplit(f"//{bare}")
    if parsed.hostname is None:
        raise TargetError("hostname is missing")
    return parsed.hostname.lower()

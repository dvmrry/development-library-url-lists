"""Deterministic extraction of package-repository URLs from known config shapes."""

from __future__ import annotations

import json
import re
import tomllib
import xml.etree.ElementTree as ElementTree
from typing import Any, Callable, Iterable

from .normalize import extract_urls


SUPPORTED_EXTRACTORS = frozenset(
    {
        "bunfig-toml",
        "cargo-toml",
        "composer-json",
        "conan-cli",
        "conan-json",
        "conda-yaml",
        "docker-json",
        "environment-assignment",
        "gradle-repository",
        "maven-pom-xml",
        "maven-settings-xml",
        "npmrc",
        "nuget-xml",
        "pip-config",
        "r-repositories",
        "ruby-source",
        "sbt-resolver",
        "stack-yaml",
        "swift-registries-json",
        "uv-toml",
        "yarnrc-yaml",
    }
)


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def _active_lines(text: str) -> Iterable[str]:
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped.startswith(("#", ";", "//")):
            continue
        yield line


def _strip_c_style_comments(text: str) -> str:
    output: list[str] = []
    quote: str | None = None
    escaped = False
    position = 0
    while position < len(text):
        character = text[position]
        following = text[position + 1] if position + 1 < len(text) else ""
        if quote:
            output.append(character)
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            position += 1
            continue
        if character in {"'", '"'}:
            quote = character
            output.append(character)
            position += 1
            continue
        if character == "/" and following == "/":
            position += 2
            while position < len(text) and text[position] not in "\r\n":
                position += 1
            continue
        if character == "/" and following == "*":
            position += 2
            while position < len(text) - 1 and text[position : position + 2] != "*/":
                if text[position] in "\r\n":
                    output.append(text[position])
                position += 1
            position = min(position + 2, len(text))
            continue
        output.append(character)
        position += 1
    return "".join(output)


def _urls_from_assignment_lines(text: str, pattern: re.Pattern[str]) -> list[str]:
    values: list[str] = []
    for line in _active_lines(text):
        match = pattern.match(line)
        if match:
            values.extend(extract_urls(match.group("value")))
    return _unique(values)


def _extract_npmrc(text: str, _: tuple[str, ...]) -> list[str]:
    pattern = re.compile(
        r"^\s*(?:@[^:\s]+:)?registry\s*=\s*(?P<value>.+)$",
        re.IGNORECASE,
    )
    return _urls_from_assignment_lines(text, pattern)


def _extract_yarnrc(text: str, _: tuple[str, ...]) -> list[str]:
    pattern = re.compile(
        r"^\s*npmRegistryServer\s*:\s*(?P<value>.+)$",
        re.IGNORECASE,
    )
    return _urls_from_assignment_lines(text, pattern)


def _urls_from_values(values: Iterable[Any]) -> list[str]:
    urls: list[str] = []
    for value in values:
        if isinstance(value, str):
            urls.extend(extract_urls(value))
        elif isinstance(value, list):
            urls.extend(
                url
                for item in value
                if isinstance(item, str)
                for url in extract_urls(item)
            )
    return _unique(urls)


def _load_toml(text: str) -> dict[str, Any] | None:
    try:
        value = tomllib.loads(text)
    except (RecursionError, tomllib.TOMLDecodeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _extract_bunfig(text: str, _: tuple[str, ...]) -> list[str]:
    document = _load_toml(text)
    if document is None:
        return []
    install = document.get("install", {})
    if not isinstance(install, dict):
        return []
    return _urls_from_values([install.get("registry")])


def _extract_pip_config(text: str, _: tuple[str, ...]) -> list[str]:
    pattern = re.compile(
        r"^\s*(?:extra-index-url|index-url)\s*=\s*(?P<value>.*)$",
        re.IGNORECASE,
    )
    urls: list[str] = []
    continuation_indent: int | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith(("#", ";")):
            continue
        match = pattern.match(line)
        if match:
            continuation_indent = len(line) - len(stripped)
            urls.extend(extract_urls(match.group("value")))
            continue
        indentation = len(line) - len(stripped)
        if continuation_indent is not None and indentation > continuation_indent:
            urls.extend(extract_urls(stripped))
        else:
            continuation_indent = None
    return _unique(urls)


def _extract_uv_toml(text: str, _: tuple[str, ...]) -> list[str]:
    document = _load_toml(text)
    if document is None:
        return []
    tool = document.get("tool", {})
    uv = tool.get("uv", {}) if isinstance(tool, dict) else {}
    if not isinstance(uv, dict):
        return []
    values: list[Any] = [uv.get("index-url"), uv.get("extra-index-url")]
    indexes = uv.get("index", [])
    if isinstance(indexes, dict):
        indexes = [indexes]
    if isinstance(indexes, list):
        values.extend(
            item.get("url")
            for item in indexes
            if isinstance(item, dict)
        )
    return _urls_from_values(values)


def _extract_conda_yaml(text: str, _: tuple[str, ...]) -> list[str]:
    scalar_fields = {"channel_alias"}
    block_fields = {
        "channels",
        "custom_channels",
        "custom_multichannels",
        "default_channels",
        "migrated_channel_aliases",
        "migrated_custom_channels",
    }
    urls: list[str] = []
    active_indent: int | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indentation = len(line) - len(stripped)
        field = re.match(
            r"^(?P<field>[a-z_]+)\s*:\s*(?P<value>.*)$",
            stripped,
            re.IGNORECASE,
        )
        if field and field.group("field").lower() in scalar_fields | block_fields:
            field_name = field.group("field").lower()
            value = field.group("value").split(" #", 1)[0]
            urls.extend(extract_urls(value))
            active_indent = indentation if field_name in block_fields else None
            continue
        if active_indent is not None and indentation > active_indent:
            urls.extend(extract_urls(stripped.split(" #", 1)[0]))
            continue
        active_indent = None
    return _unique(urls)


def _local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _walk_xml(
    element: ElementTree.Element,
    path: tuple[str, ...] = (),
) -> Iterable[tuple[tuple[str, ...], ElementTree.Element]]:
    stack = [(element, path)]
    while stack:
        current_element, parent_path = stack.pop()
        current_path = (*parent_path[-2:], _local_tag(current_element.tag))
        yield current_path, current_element
        stack.extend(
            (child, current_path) for child in reversed(list(current_element))
        )


def _xml_document(text: str) -> ElementTree.Element | None:
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", text, re.IGNORECASE):
        return None
    try:
        return ElementTree.fromstring(text)
    except (ElementTree.ParseError, RecursionError, ValueError):
        return None


def _path_has_suffix(path: tuple[str, ...], suffix: tuple[str, ...]) -> bool:
    return len(path) >= len(suffix) and path[-len(suffix) :] == suffix


def _extract_xml_text_paths(
    text: str,
    allowed_suffixes: set[tuple[str, ...]],
) -> list[str]:
    root = _xml_document(text)
    if root is None:
        return []
    urls: list[str] = []
    for path, element in _walk_xml(root):
        if any(_path_has_suffix(path, suffix) for suffix in allowed_suffixes):
            urls.extend(extract_urls(element.text or ""))
    return _unique(urls)


def _extract_maven_pom(text: str, _: tuple[str, ...]) -> list[str]:
    return _extract_xml_text_paths(
        text,
        {
            ("repositories", "repository", "url"),
            ("pluginrepositories", "pluginrepository", "url"),
            ("distributionmanagement", "repository", "url"),
            ("distributionmanagement", "snapshotrepository", "url"),
        },
    )


def _extract_maven_settings(text: str, _: tuple[str, ...]) -> list[str]:
    return _extract_xml_text_paths(
        text,
        {
            ("mirrors", "mirror", "url"),
            ("repositories", "repository", "url"),
            ("pluginrepositories", "pluginrepository", "url"),
        },
    )


def _extract_gradle(text: str, _: tuple[str, ...]) -> list[str]:
    urls: list[str] = []
    active_depth: int | None = None
    for line in _active_lines(_strip_c_style_comments(text)):
        direct = re.finditer(
            r"\bmaven\s*\(\s*['\"](?P<url>https?://[^'\"]+)",
            line,
            re.IGNORECASE,
        )
        urls.extend(match.group("url") for match in direct)

        opens = line.count("{")
        closes = line.count("}")
        starts_block = re.search(r"\bmaven\s*\{", line, re.IGNORECASE)
        started_here = active_depth is None and starts_block is not None
        if active_depth is None and starts_block:
            active_depth = opens - closes
        if active_depth is not None:
            if re.search(r"\b(?:url|setUrl|uri)\b", line, re.IGNORECASE):
                urls.extend(extract_urls(line))
            if not started_here:
                active_depth += opens - closes
            if active_depth <= 0:
                active_depth = None
    return _unique(urls)


def _extract_sbt(text: str, _: tuple[str, ...]) -> list[str]:
    urls: list[str] = []
    active_depth = 0
    for line in _active_lines(_strip_c_style_comments(text)):
        is_resolver = re.search(r"\bresolvers?\b", line, re.IGNORECASE) is not None
        if is_resolver:
            active_depth = max(
                0,
                line.count("(")
                + line.count("{")
                - line.count(")")
                - line.count("}"),
            )
            urls.extend(extract_urls(line))
            continue
        if active_depth > 0:
            urls.extend(extract_urls(line))
            active_depth += line.count("(") + line.count("{")
            active_depth -= line.count(")") + line.count("}")
    return _unique(urls)


def _extract_nuget(text: str, _: tuple[str, ...]) -> list[str]:
    root = _xml_document(text)
    if root is None:
        return []
    urls: list[str] = []
    for path, element in _walk_xml(root):
        if _path_has_suffix(path, ("packagesources", "add")):
            urls.extend(extract_urls(element.attrib.get("value", "")))
    return _unique(urls)


def _extract_cargo(text: str, _: tuple[str, ...]) -> list[str]:
    document = _load_toml(text)
    if document is None:
        return []
    values: list[Any] = []
    registries = document.get("registries", {})
    if isinstance(registries, dict):
        values.extend(
            item.get("index")
            for item in registries.values()
            if isinstance(item, dict)
        )
    sources = document.get("source", {})
    if isinstance(sources, dict):
        values.extend(
            item.get("registry")
            for item in sources.values()
            if isinstance(item, dict)
        )
    return _urls_from_values(values)


def _extract_environment(text: str, keys: tuple[str, ...]) -> list[str]:
    if not keys:
        return []
    key_expression = "|".join(re.escape(key) for key in keys)
    pattern = re.compile(
        rf"(?<![A-Za-z0-9_])(?P<key>{key_expression})\s*(?:=|:)\s*(?P<value>.+)$",
        re.IGNORECASE,
    )
    urls: list[str] = []
    for line in _active_lines(text):
        match = pattern.search(line)
        if not match:
            continue
        value = match.group("value").strip()
        if value.startswith(("'", '"', "`")):
            quote = value[0]
            closing = value.find(quote, 1)
            value = value[1:closing] if closing > 0 else value[1:]
        else:
            parts = value.split()
            if not parts:
                continue
            value = parts[0]
        values = (
            re.split(r"[,|]", value)
            if match.group("key").upper() == "GOPROXY"
            else [value]
        )
        for item in values:
            urls.extend(extract_urls(item))
    return _unique(urls)


def _extract_composer(text: str, _: tuple[str, ...]) -> list[str]:
    try:
        document = json.loads(text)
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError):
        return []
    repositories = document.get("repositories", []) if isinstance(document, dict) else []
    if isinstance(repositories, dict):
        repositories = list(repositories.values())
    if not isinstance(repositories, list):
        return []
    values = [
        item.get("url")
        for item in repositories
        if isinstance(item, dict)
        and str(item.get("type", "")).lower() == "composer"
    ]
    return _urls_from_values(values)


def _extract_ruby_source(text: str, _: tuple[str, ...]) -> list[str]:
    pattern = re.compile(
        r"^\s*source\s*(?:\(\s*)?['\"](?P<value>https?://[^'\"]+)",
        re.IGNORECASE,
    )
    return _urls_from_assignment_lines(text, pattern)


def _extract_conan_cli(text: str, _: tuple[str, ...]) -> list[str]:
    urls: list[str] = []
    pattern = re.compile(r"\bconan\s+remote\s+add\b", re.IGNORECASE)
    for line in _active_lines(text):
        match = pattern.search(line)
        if match:
            discovered = extract_urls(line[match.end() :])
            if discovered:
                urls.append(discovered[0])
    return _unique(urls)


def _extract_conan_json(text: str, _: tuple[str, ...]) -> list[str]:
    try:
        document = json.loads(text)
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError):
        return []
    remotes = document.get("remotes", []) if isinstance(document, dict) else []
    if isinstance(remotes, dict):
        remotes = list(remotes.values())
    if not isinstance(remotes, list):
        return []
    return _urls_from_values(
        item.get("url") for item in remotes if isinstance(item, dict)
    )


def _extract_stack_yaml(text: str, _: tuple[str, ...]) -> list[str]:
    urls: list[str] = []
    active_indent: int | None = None
    for line in text.splitlines():
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indentation = len(line) - len(stripped)
        if re.match(r"^package-indices\s*:", stripped, re.IGNORECASE):
            active_indent = indentation
            continue
        if active_indent is not None and indentation > active_indent:
            match = re.match(
                r"^-?\s*download-prefix\s*:\s*(?P<value>.+)$",
                stripped,
                re.IGNORECASE,
            )
            if match:
                urls.extend(extract_urls(match.group("value")))
            continue
        active_indent = None
    return _unique(urls)


def _balanced_delimiter(
    text: str,
    start: int,
    opening: str,
    closing: str,
    *,
    max_scan: int = 10_000,
) -> str:
    """Return a balanced slice, scanning at most max_scan characters.

    The scan bound keeps a hostile file full of unbalanced delimiters from
    turning repeated calls into quadratic work; real configuration values
    balance within a few hundred characters.
    """

    depth = 0
    quote: str | None = None
    escaped = False
    for position in range(start, min(len(text), start + max_scan)):
        character = text[position]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character == opening:
            depth += 1
        elif character == closing:
            depth -= 1
            if depth == 0:
                return text[start : position + 1]
    return text[start : start + 4_000]


def _balanced_call(text: str, start: int) -> str:
    return _balanced_delimiter(text, start, "(", ")")


def _assignment_value(text: str, start: int) -> str:
    depth = 0
    quote: str | None = None
    escaped = False
    for position in range(start, len(text)):
        character = text[position]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character in "([{":
            depth += 1
        elif character in ")]}":
            if depth == 0:
                return text[start:position]
            depth -= 1
        elif character == "," and depth == 0:
            return text[start:position]
    return text[start:]


_MAX_R_OPTION_CALLS = 100


def _extract_r_repositories(text: str, _: tuple[str, ...]) -> list[str]:
    urls: list[str] = []
    active_text = "\n".join(_active_lines(text))
    matches = re.finditer(r"\boptions\s*\(", active_text, re.IGNORECASE)
    for index, match in enumerate(matches):
        if index >= _MAX_R_OPTION_CALLS:
            break
        call = _balanced_call(active_text, match.end() - 1)
        assignment = re.search(r"(?:^|[(,\s])repos\s*=", call, re.IGNORECASE)
        if assignment:
            urls.extend(extract_urls(_assignment_value(call, assignment.end())))
    indexed_assignment = re.compile(
        r"^\s*repos\s*\[\s*(?:\[\s*)?['\"][^'\"]+['\"]\s*"
        r"(?:\]\s*)?\]\s*<-\s*(?P<value>.+)$",
        re.IGNORECASE,
    )
    urls.extend(_urls_from_assignment_lines(text, indexed_assignment))
    return _unique(urls)


def _extract_swift_registries(text: str, _: tuple[str, ...]) -> list[str]:
    try:
        document = json.loads(text)
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError):
        return []
    registries = document.get("registries", {}) if isinstance(document, dict) else {}
    if not isinstance(registries, dict):
        return []
    return _urls_from_values(
        item.get("url")
        for item in registries.values()
        if isinstance(item, dict)
    )


def _extract_docker(text: str, _: tuple[str, ...]) -> list[str]:
    try:
        document = json.loads(text)
    except (json.JSONDecodeError, RecursionError, UnicodeError, ValueError):
        document = None
    if isinstance(document, dict):
        mirrors = document.get("registry-mirrors", [])
        if not isinstance(mirrors, list):
            return []
        return _urls_from_values([mirrors])

    match = re.search(
        r"(?m)^\s*['\"]registry-mirrors['\"]\s*:\s*(?P<open>\[)",
        text,
    )
    if not match:
        return []
    array = _balanced_delimiter(text, match.start("open"), "[", "]")
    return _unique(extract_urls(array))


Extractor = Callable[[str, tuple[str, ...]], list[str]]

_EXTRACTORS: dict[str, Extractor] = {
    "bunfig-toml": _extract_bunfig,
    "cargo-toml": _extract_cargo,
    "composer-json": _extract_composer,
    "conan-cli": _extract_conan_cli,
    "conan-json": _extract_conan_json,
    "conda-yaml": _extract_conda_yaml,
    "docker-json": _extract_docker,
    "environment-assignment": _extract_environment,
    "gradle-repository": _extract_gradle,
    "maven-pom-xml": _extract_maven_pom,
    "maven-settings-xml": _extract_maven_settings,
    "npmrc": _extract_npmrc,
    "nuget-xml": _extract_nuget,
    "pip-config": _extract_pip_config,
    "r-repositories": _extract_r_repositories,
    "ruby-source": _extract_ruby_source,
    "sbt-resolver": _extract_sbt,
    "stack-yaml": _extract_stack_yaml,
    "swift-registries-json": _extract_swift_registries,
    "uv-toml": _extract_uv_toml,
    "yarnrc-yaml": _extract_yarnrc,
}


def extract_registry_urls(
    text: str,
    extractor: str,
    *,
    keys: Iterable[str] = (),
) -> list[str]:
    """Extract only URLs occupying a known package-manager configuration field."""

    function = _EXTRACTORS.get(extractor)
    if function is None:
        raise ValueError(f"unsupported discovery extractor: {extractor}")
    return function(text, tuple(keys))

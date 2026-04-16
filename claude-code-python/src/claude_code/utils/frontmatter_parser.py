"""
Python port of: src/utils/frontmatterParser.ts
Parses YAML frontmatter delimited by '---' from Markdown files.

Note: logForDebugging calls are replaced with stdlib logging warnings.
      HooksSettings is represented as a plain dict.
"""

from __future__ import annotations

import logging
import re
import warnings
from typing import Any, Dict, List, Optional, Union

try:
    import yaml as _yaml

    def _parse_yaml(text: str) -> Any:
        return _yaml.safe_load(text)

except ImportError:  # pragma: no cover
    def _parse_yaml(text: str) -> Any:  # type: ignore[misc]
        raise ImportError("PyYAML is required: pip install pyyaml")


logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Type aliases / TypedDicts
# ---------------------------------------------------------------------------

# HooksSettings: keys are hook event names, values are lists of matcher configs.
HooksSettings = Dict[str, Any]


class FrontmatterData(dict):
    """
    Dict subclass representing parsed YAML frontmatter.

    Keeps the same structure as the TS FrontmatterData type; all keys are
    optional and the dict can hold arbitrary extra keys.
    """


class ParsedMarkdown:
    """Container for parsed frontmatter + remaining content."""

    __slots__ = ("frontmatter", "content")

    def __init__(self, frontmatter: FrontmatterData, content: str) -> None:
        self.frontmatter = frontmatter
        self.content = content

    def __repr__(self) -> str:  # pragma: no cover
        return f"ParsedMarkdown(frontmatter={dict(self.frontmatter)!r}, content={self.content[:40]!r})"


# ---------------------------------------------------------------------------
# YAML special-character quoting
# ---------------------------------------------------------------------------

# Characters / patterns that require quoting in unquoted YAML scalar values
_YAML_SPECIAL_CHARS = re.compile(r'[{}[\]*&#!|>%@`]|: ')


def _quote_problematic_values(frontmatter_text: str) -> str:
    """
    Pre-process frontmatter text so that values containing YAML special
    characters are double-quoted.  Mirrors the TS quoteProblematicValues().
    """
    lines = frontmatter_text.split("\n")
    result: List[str] = []

    for line in lines:
        m = re.match(r'^([a-zA-Z_-]+):\s+(.+)$', line)
        if m:
            key, value = m.group(1), m.group(2)
            # Already quoted?
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                result.append(line)
                continue
            # Needs quoting?
            if _YAML_SPECIAL_CHARS.search(value):
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                result.append(f'{key}: "{escaped}"')
                continue
        result.append(line)

    return "\n".join(result)


# ---------------------------------------------------------------------------
# Core parser
# ---------------------------------------------------------------------------

FRONTMATTER_REGEX = re.compile(r'^---\s*\n([\s\S]*?)---\s*\n?')


def parse_frontmatter(
    markdown: str,
    source_path: Optional[str] = None,
) -> ParsedMarkdown:
    """
    Parse markdown content to extract YAML frontmatter and body.

    Args:
        markdown:    Raw markdown string.
        source_path: Optional file path, used only for log messages.

    Returns:
        ParsedMarkdown with .frontmatter (FrontmatterData) and .content (str).
    """
    m = FRONTMATTER_REGEX.match(markdown)

    if not m:
        return ParsedMarkdown(frontmatter=FrontmatterData(), content=markdown)

    frontmatter_text: str = m.group(1) or ""
    content: str = markdown[m.end():]

    frontmatter = FrontmatterData()

    def _try_parse(text: str) -> Optional[FrontmatterData]:
        parsed = _parse_yaml(text)
        if parsed and isinstance(parsed, dict) and not isinstance(parsed, list):
            return FrontmatterData(parsed)
        return None

    try:
        result = _try_parse(frontmatter_text)
        if result is not None:
            frontmatter = result
    except Exception:
        # First parse failed — retry with quoted values
        try:
            quoted = _quote_problematic_values(frontmatter_text)
            result = _try_parse(quoted)
            if result is not None:
                frontmatter = result
        except Exception as retry_err:
            location = f" in {source_path}" if source_path else ""
            logger.warning(
                "Failed to parse YAML frontmatter%s: %s", location, retry_err
            )

    return ParsedMarkdown(frontmatter=frontmatter, content=content)


# ---------------------------------------------------------------------------
# Path splitting with brace expansion
# ---------------------------------------------------------------------------

def split_path_in_frontmatter(input_: Union[str, List[str]]) -> List[str]:
    """
    Split a comma-separated glob string and expand brace patterns.
    Commas inside braces are not treated as separators.
    Also accepts a list of strings for ergonomic frontmatter.

    Examples::

        split_path_in_frontmatter("a, b")                 # ["a", "b"]
        split_path_in_frontmatter("a, src/*.{ts,tsx}")    # ["a", "src/*.ts", "src/*.tsx"]
        split_path_in_frontmatter("{a,b}/{c,d}")          # ["a/c", "a/d", "b/c", "b/d"]
        split_path_in_frontmatter(["a", "src/*.{ts,tsx}"]) # ["a", "src/*.ts", "src/*.tsx"]
    """
    if isinstance(input_, list):
        result: List[str] = []
        for item in input_:
            result.extend(split_path_in_frontmatter(item))
        return result

    if not isinstance(input_, str):
        return []

    # Split by comma while respecting brace depth
    parts: List[str] = []
    current = ""
    brace_depth = 0

    for ch in input_:
        if ch == "{":
            brace_depth += 1
            current += ch
        elif ch == "}":
            brace_depth -= 1
            current += ch
        elif ch == "," and brace_depth == 0:
            trimmed = current.strip()
            if trimmed:
                parts.append(trimmed)
            current = ""
        else:
            current += ch

    trimmed = current.strip()
    if trimmed:
        parts.append(trimmed)

    # Expand brace patterns in each part
    expanded: List[str] = []
    for part in parts:
        if part:
            expanded.extend(_expand_braces(part))
    return expanded


def _expand_braces(pattern: str) -> List[str]:
    """
    Recursively expand brace patterns in a glob string.

    Examples::

        _expand_braces("src/*.{ts,tsx}") -> ["src/*.ts", "src/*.tsx"]
        _expand_braces("{a,b}/{c,d}")    -> ["a/c", "a/d", "b/c", "b/d"]
    """
    m = re.match(r'^([^{]*)\{([^}]+)\}(.*)$', pattern)
    if not m:
        return [pattern]

    prefix = m.group(1) or ""
    alternatives = m.group(2) or ""
    suffix = m.group(3) or ""

    results: List[str] = []
    for alt in alternatives.split(","):
        combined = prefix + alt.strip() + suffix
        results.extend(_expand_braces(combined))
    return results


# ---------------------------------------------------------------------------
# Utility parsers
# ---------------------------------------------------------------------------

def parse_positive_int_from_frontmatter(value: Any) -> Optional[int]:
    """
    Parse a positive integer from a raw frontmatter value.
    Handles both int and string representations.
    Returns None if invalid or absent.
    """
    if value is None:
        return None
    if isinstance(value, int):
        parsed = value
    else:
        try:
            parsed = int(str(value), 10)
        except (ValueError, TypeError):
            return None
    if isinstance(parsed, int) and parsed > 0:
        return parsed
    return None


def coerce_description_to_string(
    value: Any,
    component_name: Optional[str] = None,
    plugin_name: Optional[str] = None,
) -> Optional[str]:
    """
    Validate and coerce a description value from frontmatter.

    - Strings are returned trimmed (None if empty).
    - Numbers/booleans are coerced via str().
    - Non-scalar (list/dict) values are logged and omitted.
    - None/null returns None.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, (int, float, bool)):
        return str(value)
    # Non-scalar
    source = (
        f"{plugin_name}:{component_name}"
        if plugin_name
        else (component_name or "unknown")
    )
    logger.warning("Description invalid for %s - omitting", source)
    return None


def parse_boolean_frontmatter(value: Any) -> bool:
    """Return True only for literal True or the string 'true'."""
    return value is True or value == "true"


# ---------------------------------------------------------------------------
# Shell frontmatter
# ---------------------------------------------------------------------------

FrontmatterShell = str  # 'bash' | 'powershell'
_FRONTMATTER_SHELLS: tuple[str, ...] = ("bash", "powershell")


def parse_shell_frontmatter(
    value: Any,
    source: str,
) -> Optional[FrontmatterShell]:
    """
    Parse and validate the 'shell:' frontmatter field.

    Returns None for absent/null/empty (caller defaults to bash).
    Logs a warning and returns None for unrecognised values.
    """
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if not normalized:
        return None
    if normalized in _FRONTMATTER_SHELLS:
        return normalized
    logger.warning(
        "Frontmatter 'shell: %s' in %s is not recognized. "
        "Valid values: %s. Falling back to bash.",
        value,
        source,
        ", ".join(_FRONTMATTER_SHELLS),
    )
    return None

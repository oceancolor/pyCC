"""
Debug output filtering utilities.
Ported from debugFilter.ts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class DebugFilter:
    include: list[str] = field(default_factory=list)
    exclude: list[str] = field(default_factory=list)
    is_exclusive: bool = False


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

@lru_cache(maxsize=128)
def parse_debug_filter(filter_string: Optional[str] = None) -> Optional[DebugFilter]:
    """
    Parse a debug filter string into a DebugFilter configuration.

    Examples:
      "api,hooks"   -> include only api and hooks categories
      "!1p,!file"   -> exclude 1p and file categories
      None / ""     -> no filtering (show all)
    """
    if not filter_string or not filter_string.strip():
        return None

    parts = [f.strip() for f in filter_string.split(",") if f.strip()]
    if not parts:
        return None

    has_exclusive = any(f.startswith("!") for f in parts)
    has_inclusive = any(not f.startswith("!") for f in parts)

    # Mixed mode is unsupported – show everything
    if has_exclusive and has_inclusive:
        return None

    clean = [f.lstrip("!").lower() for f in parts]

    return DebugFilter(
        include=[] if has_exclusive else clean,
        exclude=clean if has_exclusive else [],
        is_exclusive=has_exclusive,
    )


# ---------------------------------------------------------------------------
# Category extraction
# ---------------------------------------------------------------------------

def extract_debug_categories(message: str) -> list[str]:
    """
    Extract debug categories from a message.

    Supports patterns:
      - "category: message"
      - "[CATEGORY] message"
      - 'MCP server "name": message'
      - "[ANT-ONLY] 1P event: ..." → ["ant-only", "1p"]
    """
    categories: list[str] = []

    # Pattern: MCP server "servername" — check first to avoid false positives
    mcp_match = re.match(r'^MCP server ["\']([^"\']+)["\']', message)
    if mcp_match:
        categories.append("mcp")
        categories.append(mcp_match.group(1).lower())
    else:
        # Pattern: "category: message" (simple prefix)
        prefix_match = re.match(r"^([^:\[]+):", message)
        if prefix_match:
            categories.append(prefix_match.group(1).strip().lower())

    # Pattern: [CATEGORY] at the start
    bracket_match = re.match(r"^\[([^\]]+)]", message)
    if bracket_match:
        categories.append(bracket_match.group(1).strip().lower())

    # Pattern: 1P event shorthand
    if "1p event:" in message.lower():
        categories.append("1p")

    # Secondary categories – e.g. "AutoUpdaterWrapper: Installation type: development"
    secondary_match = re.search(
        r":\s*([^:]+?)(?:\s+(?:type|mode|status|event))?:", message
    )
    if secondary_match:
        secondary = secondary_match.group(1).strip().lower()
        if len(secondary) < 30 and " " not in secondary:
            categories.append(secondary)

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[str] = []
    for cat in categories:
        if cat not in seen:
            seen.add(cat)
            result.append(cat)
    return result


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------

def should_show_debug_categories(
    categories: list[str],
    filter_cfg: Optional[DebugFilter],
) -> bool:
    """Return True if a message with the given categories should be shown."""
    if filter_cfg is None:
        return True

    if not categories:
        return False  # Uncategorized messages are hidden when a filter is active

    if filter_cfg.is_exclusive:
        return not any(cat in filter_cfg.exclude for cat in categories)
    else:
        return any(cat in filter_cfg.include for cat in categories)


def should_show_debug_message(
    message: str,
    filter_cfg: Optional[DebugFilter],
) -> bool:
    """Main entry point: check whether a debug message should be shown."""
    if filter_cfg is None:
        return True
    categories = extract_debug_categories(message)
    return should_show_debug_categories(categories, filter_cfg)


def filter_output(lines: list[str], filter_cfg: Optional[DebugFilter]) -> list[str]:
    """Filter a list of output lines, returning only those that should be shown."""
    if filter_cfg is None:
        return lines
    return [line for line in lines if should_show_debug_message(line, filter_cfg)]

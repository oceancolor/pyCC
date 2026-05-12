"""
Session-scoped tool schema cache.
Ported from utils/toolSchemaCache.ts

Memoizes rendered tool schemas per-session to avoid cache busting when
GrowthBook gates flip, MCP servers reconnect, or dynamic content changes.
Lives in a leaf module so auth can clear it without creating circular imports.
"""
from __future__ import annotations

from typing import Any, Dict

# Session-scoped cache: tool_name → rendered schema dict
_TOOL_SCHEMA_CACHE: Dict[str, Any] = {}


def get_tool_schema_cache() -> Dict[str, Any]:
    """Return the module-level tool schema cache (mutable)."""
    return _TOOL_SCHEMA_CACHE


def clear_tool_schema_cache() -> None:
    """Clear all cached tool schemas (e.g., on auth changes or MCP reconnects)."""
    _TOOL_SCHEMA_CACHE.clear()

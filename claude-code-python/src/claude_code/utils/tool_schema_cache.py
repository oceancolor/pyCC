"""Session-scoped tool schema cache. Ported from toolSchemaCache.ts.

Session-scoped cache of rendered tool schemas.  Tool schemas render at server
position 2 (before system prompt), so any byte-level change busts the entire
~11K-token tool block AND everything downstream.  GrowthBook gate flips,
MCP reconnects, or dynamic content in tool.prompt() all cause this churn.
Memoizing per-session locks the schema bytes at first render — mid-session
refreshes no longer bust the cache.

Lives in a leaf module so auth.py can clear it without importing api.py
(which would create a cycle via plans→settings→file→growthbook→config→
bridgeEnabled→auth).
"""
from __future__ import annotations

from typing import Any, Dict, Iterator, Optional

__all__ = [
    "get_tool_schema_cache",
    "get_cached_schema",
    "set_cached_schema",
    "clear_tool_schema_cache",
    "has_cached_schema",
    "iter_cached_schemas",
]

# Module-level singleton — intentionally not hidden behind a class so auth.py
# can call clear_tool_schema_cache() as a one-liner.
_TOOL_SCHEMA_CACHE: Dict[str, Any] = {}


def get_tool_schema_cache() -> Dict[str, Any]:
    """Return the module-level tool schema cache (mutable reference)."""
    return _TOOL_SCHEMA_CACHE


def get_cached_schema(tool_name: str) -> Optional[Any]:
    """Return the cached schema for *tool_name*, or None if not cached."""
    return _TOOL_SCHEMA_CACHE.get(tool_name)


def set_cached_schema(tool_name: str, schema: Any) -> None:
    """Store *schema* under *tool_name* in the cache."""
    _TOOL_SCHEMA_CACHE[tool_name] = schema


def has_cached_schema(tool_name: str) -> bool:
    """Return True if a schema for *tool_name* is already cached."""
    return tool_name in _TOOL_SCHEMA_CACHE


def clear_tool_schema_cache() -> None:
    """Clear all cached tool schemas.

    Called by auth.py when credentials change (e.g., token refresh) to ensure
    any permission-sensitive tool properties are re-evaluated.
    """
    _TOOL_SCHEMA_CACHE.clear()


def iter_cached_schemas() -> Iterator[tuple[str, Any]]:
    """Iterate over (tool_name, schema) pairs in the cache."""
    return iter(_TOOL_SCHEMA_CACHE.items())


def cache_size() -> int:
    """Return the number of cached schemas."""
    return len(_TOOL_SCHEMA_CACHE)

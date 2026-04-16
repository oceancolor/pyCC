"""Tool schema cache. Ported from toolSchemaCache.ts"""
from __future__ import annotations
from typing import Any, Dict
_TOOL_SCHEMA_CACHE: Dict[str, Any] = {}

def get_tool_schema_cache() -> Dict[str, Any]:
    return _TOOL_SCHEMA_CACHE

def clear_tool_schema_cache() -> None:
    _TOOL_SCHEMA_CACHE.clear()

"""Shared tool utilities. Ported from tools/utils.ts"""
from __future__ import annotations
from typing import Any, List, Optional


def get_tool_by_name(tools: List[Any], name: str) -> Optional[Any]:
    for t in tools:
        if getattr(t, "name", None) == name:
            return t
    return None


def tool_matches_name(tool: Any, name: str) -> bool:
    return getattr(tool, "name", None) == name

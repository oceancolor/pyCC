"""Shared tool utilities. Ported from tools/utils.ts"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def get_tool_by_name(tools: List[Any], name: str) -> Optional[Any]:
    """Return the first tool in *tools* whose name matches *name*, or None."""
    for t in tools:
        if getattr(t, "name", None) == name:
            return t
    return None


def tool_matches_name(tool: Any, name: str) -> bool:
    """Return True if *tool*'s name attribute equals *name*."""
    return getattr(tool, "name", None) == name


def filter_tools_by_names(tools: List[Any], names: List[str]) -> List[Any]:
    """Return a list of tools whose names are in *names*."""
    name_set = set(names)
    return [t for t in tools if getattr(t, "name", None) in name_set]


def get_tool_names(tools: List[Any]) -> List[str]:
    """Return a list of tool names from *tools*."""
    return [getattr(t, "name", "") for t in tools if getattr(t, "name", None)]


def build_tool_map(tools: List[Any]) -> Dict[str, Any]:
    """Return a dict mapping tool name → tool."""
    return {getattr(t, "name", ""): t for t in tools if getattr(t, "name", None)}

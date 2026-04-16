"""MCP tool collapse classification. Ported from MCPTool/classifyForCollapse.ts (stub)."""
from __future__ import annotations
from typing import Optional


def classify_for_collapse(tool_name: str, tool_use: dict) -> Optional[str]:
    """
    Return a collapse key if this tool use can be collapsed with others of the same key.
    Returns None if the tool use should never be collapsed.
    """
    return None  # Default: no collapsing

"""MCPTool alias package (top-level mcp_tool directory).

Re-exports MCPTool and helpers from the canonical ``mcp_tool`` implementation.
Also re-exports the ``classify_mcp_tool_for_collapse`` helper used by the
UI to decide whether a tool-use block can be collapsed in the diff view.

Ported from: tools/MCPTool/ (TypeScript)

Usage::

    from claude_code.tools.mcp_tool import (
        MCPTool,
        MCP_TOOL_NAME_PREFIX,
        make_mcp_tool_name,
        classify_mcp_tool_for_collapse,
    )
"""
from __future__ import annotations

from claude_code.tools.mcp_tool.mcp_tool import MCPTool, MCP_TOOL_NAME_PREFIX, make_mcp_tool_name
from claude_code.tools.mcp_tool.classify_for_collapse import classify_mcp_tool_for_collapse

__all__ = [
    "MCPTool",
    "MCP_TOOL_NAME_PREFIX",
    "make_mcp_tool_name",
    "classify_mcp_tool_for_collapse",
]

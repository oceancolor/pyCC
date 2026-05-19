"""MCPTool package (m_c_p_tool directory).

Re-exports MCPTool, the MCP tool name prefix, and the helper used to
build namespaced MCP tool names.

MCPTool wraps calls to tools provided by connected MCP (Model Context
Protocol) servers.  Each MCP server exposes its own set of tools that are
registered with the ``mcp__<server>__<tool>`` naming convention.

Ported from: tools/MCPTool/ (TypeScript)

Usage::

    from claude_code.tools.m_c_p_tool import (
        MCPTool,
        MCP_TOOL_NAME_PREFIX,
        make_mcp_tool_name,
    )
"""
from __future__ import annotations

from claude_code.tools.m_c_p_tool.mcp_tool import MCPTool, MCP_TOOL_NAME_PREFIX, make_mcp_tool_name

__all__ = [
    "MCPTool",
    "MCP_TOOL_NAME_PREFIX",
    "make_mcp_tool_name",
]

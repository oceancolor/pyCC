"""ListMcpResourcesTool package.

Re-exports ListMcpResourcesTool and its canonical name constant.

ListMcpResourcesTool enumerates the resources (files, data sources, etc.)
exposed by a connected MCP (Model Context Protocol) server.

Ported from: tools/ListMcpResourcesTool/ (TypeScript)

Usage::

    from claude_code.tools.list_mcp_resources_tool import (
        ListMcpResourcesTool,
        LIST_MCP_RESOURCES_TOOL_NAME,
    )
"""
from __future__ import annotations

from claude_code.tools.list_mcp_resources_tool.list_mcp_resources_tool import (
    ListMcpResourcesTool,
    LIST_MCP_RESOURCES_TOOL_NAME,
)

__all__ = [
    "ListMcpResourcesTool",
    "LIST_MCP_RESOURCES_TOOL_NAME",
]

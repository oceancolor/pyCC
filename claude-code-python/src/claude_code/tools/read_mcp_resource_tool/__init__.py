"""ReadMcpResourceTool package.

Re-exports ReadMcpResourceTool and its canonical name constant.

ReadMcpResourceTool fetches the content of a specific resource from a
connected MCP (Model Context Protocol) server.  Use ``ListMcpResourcesTool``
first to discover available resource URIs, then ``ReadMcpResourceTool`` to
retrieve their content.

Ported from: tools/ReadMcpResourceTool/ (TypeScript)

Usage::

    from claude_code.tools.read_mcp_resource_tool import (
        ReadMcpResourceTool,
        READ_MCP_RESOURCE_TOOL_NAME,
    )
"""
from __future__ import annotations

from claude_code.tools.read_mcp_resource_tool.read_mcp_resource_tool import (
    ReadMcpResourceTool,
    READ_MCP_RESOURCE_TOOL_NAME,
)

__all__ = [
    "ReadMcpResourceTool",
    "READ_MCP_RESOURCE_TOOL_NAME",
]

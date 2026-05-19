"""McpAuthTool package.

Re-exports McpAuthTool and related helpers for MCP server authentication.

McpAuthTool handles the OAuth / token-exchange flow that some MCP servers
require before their tools can be called.  After successful authentication
the session stores the credentials so subsequent calls do not re-authenticate.

Ported from: tools/McpAuthTool/ (TypeScript)

Usage::

    from claude_code.tools.mcp_auth_tool import (
        McpAuthTool,
        McpAuthOutput,
        MCP_AUTH_TOOL_NAME_SUFFIX,
        build_mcp_tool_name,
        create_mcp_auth_tool,
    )
"""
from __future__ import annotations

from claude_code.tools.mcp_auth_tool.mcp_auth_tool import (
    McpAuthTool,
    McpAuthOutput,
    MCP_AUTH_TOOL_NAME_SUFFIX,
    build_mcp_tool_name,
    create_mcp_auth_tool,
)

__all__ = [
    "McpAuthTool",
    "McpAuthOutput",
    "MCP_AUTH_TOOL_NAME_SUFFIX",
    "build_mcp_tool_name",
    "create_mcp_auth_tool",
]

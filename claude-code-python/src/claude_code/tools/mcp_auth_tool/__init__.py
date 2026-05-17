"""McpAuthTool package. Ported from McpAuthTool/"""
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

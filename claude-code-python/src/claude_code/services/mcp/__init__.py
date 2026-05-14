"""MCP (Model Context Protocol) service sub-package.

Provides client, configuration, authentication, and transport layer
for connecting to MCP servers from Claude Code.
"""
from __future__ import annotations

from claude_code.services.mcp.types import (
    MCPConnectionStatus,
    MCPResource,
    MCPServerConfig,
    MCPTool,
)
from claude_code.services.mcp.client import (
    get_connection_timeout_ms,
    get_mcp_tool_timeout_ms,
)

__all__ = [
    "MCPServerConfig",
    "MCPTool",
    "MCPResource",
    "MCPConnectionStatus",
    "get_mcp_tool_timeout_ms",
    "get_connection_timeout_ms",
]

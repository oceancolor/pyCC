"""McpAuth tool stub. Ported from McpAuthTool."""
from __future__ import annotations
from typing import Any

MCP_AUTH_TOOL_NAME = "mcp__auth"
DESCRIPTION = "Authenticate with an MCP server that requires OAuth"


class McpAuthTool:
    name = MCP_AUTH_TOOL_NAME
    description = DESCRIPTION

    async def call(self, server: str = "", **kwargs: Any) -> dict:
        return {"error": f"MCP auth flow not available for '{server}' in this environment"}

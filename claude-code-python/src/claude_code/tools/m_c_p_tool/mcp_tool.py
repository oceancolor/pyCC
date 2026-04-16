"""MCP dynamic tool wrapper. Ported from MCPTool."""
from __future__ import annotations
from typing import Any, Optional

MCP_TOOL_NAME_PREFIX = "mcp__"


class MCPTool:
    """Proxies calls to an MCP server tool."""
    def __init__(self, tool_name: str, server_name: str, description: str,
                 input_schema: dict, client: Any = None) -> None:
        self.name = tool_name
        self.server_name = server_name
        self.description = description
        self._input_schema = input_schema
        self._client = client

    def get_schema(self) -> dict:
        return {"name": self.name, "description": self.description, "input_schema": self._input_schema}

    async def call(self, **kwargs: Any) -> dict:
        if not self._client:
            return {"error": f"MCP server '{self.server_name}' not connected"}
        try:
            return {"result": await self._client.call_tool(self.name, kwargs)}
        except Exception as e:
            return {"error": str(e)}


def make_mcp_tool_name(server_name: str, tool_name: str) -> str:
    safe = server_name.replace("-", "_").replace(" ", "_")
    return f"{MCP_TOOL_NAME_PREFIX}{safe}__{tool_name}"

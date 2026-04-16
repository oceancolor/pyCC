"""ReadMcpResource tool. Ported from ReadMcpResourceTool."""
from __future__ import annotations
from typing import Any

READ_MCP_RESOURCE_TOOL_NAME = "mcp__read_resource"
DESCRIPTION = "Read a specific resource from an MCP server by URI"
PROMPT = "Read a resource from an MCP server. Provide server name and resource URI."


class ReadMcpResourceTool:
    name = READ_MCP_RESOURCE_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "The MCP server name"},
                    "uri": {"type": "string", "description": "The resource URI to read"},
                },
                "required": ["server", "uri"]
            }
        }

    async def call(self, server: str, uri: str, mcp_clients: list = None, **kwargs: Any) -> dict:
        if not mcp_clients:
            return {"error": "No MCP clients available"}
        client = next((c for c in mcp_clients if getattr(c, "name", "") == server), None)
        if not client:
            return {"error": f"Server '{server}' not found"}
        try:
            result = await client.read_resource(uri)
            return {"content": result}
        except Exception as e:
            return {"error": str(e)}

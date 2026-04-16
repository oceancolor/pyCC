"""ListMcpResources tool. Ported from ListMcpResourcesTool."""
from __future__ import annotations
from typing import Any, List, Optional

LIST_MCP_RESOURCES_TOOL_NAME = "mcp__list_resources"
DESCRIPTION = "List available resources from connected MCP servers"
PROMPT = "List resources available from MCP servers. Optionally filter by server name."


class ListMcpResourcesTool:
    name = LIST_MCP_RESOURCES_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "server": {"type": "string", "description": "Optional server name to filter by"}
                }
            }
        }

    async def call(self, server: Optional[str] = None, mcp_clients: List[Any] = None, **kwargs: Any) -> dict:
        if not mcp_clients:
            return {"resources": []}
        resources = []
        for client in mcp_clients:
            if server and getattr(client, "name", "") != server:
                continue
            try:
                res = await client.list_resources()
                resources.extend(res)
            except Exception as e:
                pass
        return {"resources": resources}

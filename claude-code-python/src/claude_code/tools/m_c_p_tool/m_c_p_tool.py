"""MCPTool class stub. Ported from MCPTool/MCPTool.ts"""
from __future__ import annotations
from typing import Any, Optional
from claude_code.tools.m_c_p_tool.prompt import DESCRIPTION, PROMPT


class MCPTool:
    """Represents a tool provided by an MCP server.

    Each instance corresponds to one tool exposed by a configured MCP server.
    The name, description, and input schema are provided dynamically by the server.
    """

    def __init__(
        self,
        name: str,
        server_name: str,
        description: str = "",
        input_schema: Optional[dict] = None,
    ) -> None:
        self.name = name
        self.server_name = server_name
        self.description = description or DESCRIPTION
        self.input_schema = input_schema or {}

    @property
    def is_mcp(self) -> bool:
        return True

    async def call(self, **kwargs: Any) -> Any:
        """Call the underlying MCP tool via the MCP client."""
        raise NotImplementedError(
            f"MCPTool '{self.name}' from server '{self.server_name}' "
            "requires an active MCP client connection."
        )

    def __repr__(self) -> str:
        return f"MCPTool(name={self.name!r}, server={self.server_name!r})"

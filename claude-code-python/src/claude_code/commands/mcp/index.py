"""Command descriptor for /mcp. Ported from commands/mcp/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "mcp"
DESCRIPTION = "Manage MCP servers"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[enable|disable [server-name]]"
IMMEDIATE: bool = True


@dataclass
class McpCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    immediate: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /mcp command.

        Manage MCP (Model Context Protocol) servers.
        """
        return {"type": "local-command", "name": "mcp", "args": args}


default = McpCommand()

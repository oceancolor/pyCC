"""Command descriptor for /agents. Ported from commands/agents/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "agents"
DESCRIPTION = "Manage agent configurations"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class AgentsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /agents command.

        List and manage background agents.
        """
        return {"type": "local-command", "name": "agents", "args": args}


default = AgentsCommand()

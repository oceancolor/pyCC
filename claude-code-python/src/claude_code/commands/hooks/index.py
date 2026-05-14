"""Command descriptor for /hooks. Ported from commands/hooks/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "hooks"
DESCRIPTION = "View hook configurations for tool events"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
IMMEDIATE: bool = True


@dataclass
class HooksCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    immediate: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /hooks command.

        View and manage hook configurations.
        """
        return {"type": "local-command", "name": "hooks", "args": args}


default = HooksCommand()

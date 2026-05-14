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
    immediate: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /hooks command."""
        return {"type": "text", "value": f"/hooks not yet implemented"}


default = HooksCommand()

"""Command descriptor for /cost. Ported from commands/cost/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "cost"
DESCRIPTION = "Show cost of the current session"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class CostCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /cost command."""
        return {"type": "text", "value": f"/cost not yet implemented"}


default = CostCommand()

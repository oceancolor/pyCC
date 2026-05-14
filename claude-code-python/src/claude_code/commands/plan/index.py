"""Command descriptor for /plan. Ported from commands/plan/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "plan"
DESCRIPTION = "Enable plan mode or view the current session plan"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[open|<description>]"


@dataclass
class PlanCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /plan command."""
        return {"type": "text", "value": f"/plan not yet implemented"}


default = PlanCommand()

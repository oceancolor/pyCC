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
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /plan command.

        Toggle plan mode for structured edits.
        """
        return {"type": "local-command", "name": "plan", "args": args}


default = PlanCommand()

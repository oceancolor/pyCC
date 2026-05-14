"""Command descriptor for /effort. Ported from commands/effort/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "effort"
DESCRIPTION = "Set effort level for model usage"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[low|medium|high|max|auto]"


@dataclass
class EffortCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /effort command."""
        return {"type": "text", "value": f"/effort not yet implemented"}


default = EffortCommand()

"""Command descriptor for /color. Ported from commands/color/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "color"
DESCRIPTION = "Set the prompt bar color for this session"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "<color|default>"
IMMEDIATE: bool = True


@dataclass
class ColorCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    immediate: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /color command.

        Toggle or change terminal color settings.
        """
        return {"type": "local-command", "name": "color", "args": args}


default = ColorCommand()

"""Help command descriptor. Ported from commands/help/index.ts"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional

NAME = "help"
DESCRIPTION = "Show help and available commands"
TYPE: Literal["local-jsx"] = "local-jsx"
IS_HIDDEN: Optional[bool] = None


@dataclass
class HelpCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Show available commands."""
        return {"type": "text", "value": f"Help: use /help to see commands"}


default = HelpCommand()

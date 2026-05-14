"""Command descriptor for /extra-usage. Ported from commands/extra_usage/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "extra-usage"
DESCRIPTION = "Configure extra usage to keep working when limits are hit"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class ExtraUsageCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /extra-usage command.

        Show extended usage statistics.
        """
        return {"type": "local-command", "name": "extra-usage", "args": args}


default = ExtraUsageCommand()

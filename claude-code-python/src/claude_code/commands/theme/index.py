"""Command descriptor for /theme. Ported from commands/theme/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "theme"
DESCRIPTION = "Change the theme"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class ThemeCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /theme command.

        Change the Claude Code color theme.
        """
        return {"type": "local-command", "name": "theme", "args": args}


default = ThemeCommand()

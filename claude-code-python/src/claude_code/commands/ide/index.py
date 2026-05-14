"""Command descriptor for /ide. Ported from commands/ide/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "ide"
DESCRIPTION = "Manage IDE integrations and show status"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[open]"


@dataclass
class IdeCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /ide command.

        Open the current project in an IDE.
        """
        return {"type": "local-command", "name": "ide", "args": args}


default = IdeCommand()

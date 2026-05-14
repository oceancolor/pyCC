"""Command descriptor for /rename. Ported from commands/rename/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "rename"
DESCRIPTION = "Rename the current conversation"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[name]"
IMMEDIATE: bool = True


@dataclass
class RenameCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    immediate: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /rename command.

        Rename the current session.
        """
        return {"type": "local-command", "name": "rename", "args": args}


default = RenameCommand()

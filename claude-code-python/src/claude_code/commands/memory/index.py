"""Command descriptor for /memory. Ported from commands/memory/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "memory"
DESCRIPTION = "Edit Claude memory files"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class MemoryCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /memory command.

        Edit Claude memory files.
        """
        return {"type": "local-command", "name": "memory", "args": args}


default = MemoryCommand()

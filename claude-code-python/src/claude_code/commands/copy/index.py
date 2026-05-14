"""Command descriptor for /copy. Ported from commands/copy/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "copy"
DESCRIPTION = "Copy Claude's last response to clipboard (or /copy N for the Nth-latest)"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class CopyCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /copy command.

        Copy last Claude response to clipboard.
        """
        return {"type": "local-command", "name": "copy", "args": args}


default = CopyCommand()

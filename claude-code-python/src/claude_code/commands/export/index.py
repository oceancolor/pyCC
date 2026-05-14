"""Command descriptor for /export. Ported from commands/export/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "export"
DESCRIPTION = "Export the current conversation to a file or clipboard"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[filename]"


@dataclass
class ExportCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /export command."""
        return {"type": "text", "value": f"/export not yet implemented"}


default = ExportCommand()

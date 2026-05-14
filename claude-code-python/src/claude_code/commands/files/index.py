"""Command descriptor for /files. Ported from commands/files/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "files"
DESCRIPTION = "List files in the current conversation context"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False


@dataclass
class FilesCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /files command."""
        return {"type": "text", "value": f"/files not yet implemented"}


default = FilesCommand()

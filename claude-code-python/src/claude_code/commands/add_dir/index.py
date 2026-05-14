"""Command descriptor for /add-dir. Ported from commands/add_dir/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "add-dir"
DESCRIPTION = "Add a new working directory"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "<path>"


@dataclass
class AddDirCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /add-dir command."""
        return {"type": "text", "value": f"/add-dir not yet implemented"}


default = AddDirCommand()

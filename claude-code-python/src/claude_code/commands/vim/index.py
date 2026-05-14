"""Command descriptor for /vim. Ported from commands/vim/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "vim"
DESCRIPTION = "Toggle between Vim and Normal editing modes"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
SUPPORTS_NON_INTERACTIVE: bool = False


@dataclass
class VimCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /vim command."""
        return {"type": "text", "value": f"/vim not yet implemented"}


default = VimCommand()

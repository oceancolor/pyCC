"""Command descriptor for /permissions. Ported from commands/permissions/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "permissions"
DESCRIPTION = "Manage allow & deny tool permission rules"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['allowed-tools']
IS_HIDDEN: bool = False


@dataclass
class PermissionsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    aliases: List[str] = field(default_factory=lambda: ['allowed-tools'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /permissions command."""
        return {"type": "text", "value": f"/permissions not yet implemented"}


default = PermissionsCommand()

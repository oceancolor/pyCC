"""Command descriptor for /reload-plugins. Ported from commands/reload_plugins/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "reload-plugins"
DESCRIPTION = "Activate pending plugin changes in the current session"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
SUPPORTS_NON_INTERACTIVE: bool = False


@dataclass
class ReloadPluginsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /reload-plugins command."""
        return {"type": "text", "value": f"/reload-plugins not yet implemented"}


default = ReloadPluginsCommand()

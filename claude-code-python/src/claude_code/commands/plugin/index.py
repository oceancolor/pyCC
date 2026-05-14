"""Command descriptor for /plugin. Ported from commands/plugin/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "plugin"
DESCRIPTION = "Manage plugins"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class PluginCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /plugin command."""
        return {"type": "local-command", "name": "plugin", "args": args}


default = PluginCommand()

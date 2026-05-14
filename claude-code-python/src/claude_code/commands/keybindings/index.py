"""Command descriptor for /keybindings. Ported from commands/keybindings/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "keybindings"
DESCRIPTION = "Open or create your keybindings configuration file"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
SUPPORTS_NON_INTERACTIVE: bool = False


@dataclass
class KeybindingsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /keybindings command.

        Show or customize keyboard shortcuts.
        """
        return {"type": "local-command", "name": "keybindings", "args": args}


default = KeybindingsCommand()

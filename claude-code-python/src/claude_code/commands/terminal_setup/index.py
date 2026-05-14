"""Command descriptor for /terminal-setup. Ported from commands/terminal_setup/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "terminal-setup"
DESCRIPTION = "Set up terminal integration for Claude Code"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = False
SUPPORTS_NON_INTERACTIVE: bool = False


@dataclass
class TerminalSetupCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /terminal-setup command.

        Configure terminal integration.
        """
        return {"type": "local-command", "name": "terminal-setup", "args": args}


default = TerminalSetupCommand()

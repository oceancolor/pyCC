"""Command descriptor for /exit. Ported from commands/exit/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "exit"
DESCRIPTION = "Exit the REPL"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['quit']
IS_HIDDEN: bool = False
IMMEDIATE: bool = True


@dataclass
class ExitCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    aliases: List[str] = field(default_factory=lambda: ['quit'])
    immediate: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /exit command.

        Exit the current Claude Code session.
        """
        return {"type": "local-command", "name": "exit", "args": args}


default = ExitCommand()

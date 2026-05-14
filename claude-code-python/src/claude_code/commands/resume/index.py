"""Command descriptor for /resume. Ported from commands/resume/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "resume"
DESCRIPTION = "Resume a previous conversation"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['continue']
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[conversation id or search term]"


@dataclass
class ResumeCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    aliases: List[str] = field(default_factory=lambda: ['continue'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /resume command.

        Resume a previous session.
        """
        return {"type": "local-command", "name": "resume", "args": args}


default = ResumeCommand()

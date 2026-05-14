"""Command descriptor for /branch. Ported from commands/branch/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "branch"
DESCRIPTION = "Create a branch of the current conversation at this point"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = ['fork']
IS_HIDDEN: bool = False
ARGUMENT_HINT: str = "[name]"


@dataclass
class BranchCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    aliases: List[str] = field(default_factory=lambda: ['fork'])

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /branch command.

        Create or switch to a git branch.
        """
        return {"type": "local-command", "name": "branch", "args": args}


default = BranchCommand()

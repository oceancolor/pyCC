"""Command descriptor for /autofix-pr. Ported from commands/autofix_pr/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "autofix-pr"
DESCRIPTION = "Automatically fix a PR (ANT-only)"
TYPE: Literal["local"] = "local"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class AutofixPrCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /autofix-pr command."""
        return {"type": "local-command", "name": "autofix-pr", "args": args}


default = AutofixPrCommand()

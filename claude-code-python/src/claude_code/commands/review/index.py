"""Command descriptor for /review. Ported from commands/review/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "review"
DESCRIPTION = "Review code changes"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = True  # ANT-internal or advanced command


@dataclass
class ReviewCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = True

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /review command."""
        return {"type": "local-command", "name": "review", "args": args}


default = ReviewCommand()

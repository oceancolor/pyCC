"""Command descriptor for /rate-limit-options. Ported from commands/rate_limit_options/index.ts"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Literal, Optional

NAME = "rate-limit-options"
DESCRIPTION = "Show options when rate limit is reached"
TYPE: Literal["local-jsx"] = "local-jsx"
ALIASES: List[str] = []
IS_HIDDEN: bool = True


@dataclass
class RateLimitOptionsCommand:
    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    is_enabled: object = None
    is_hidden: bool = IS_HIDDEN

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /rate-limit-options command.

        Configure API rate limit handling.
        """
        return {"type": "local-command", "name": "rate-limit-options", "args": args}


default = RateLimitOptionsCommand()

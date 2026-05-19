"""Clear command descriptor. Ported from commands/clear/index.ts"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Literal

NAME = "clear"
DESCRIPTION = "Clear conversation history and free up context"
ALIASES: List[str] = ["reset", "new"]
TYPE: Literal["local"] = "local"
SUPPORTS_NON_INTERACTIVE: bool = False


@dataclass
class ClearCommand:
    """Descriptor for the /clear slash command."""

    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    aliases: List[str] = field(default_factory=lambda: ["reset", "new"])
    supports_non_interactive: bool = SUPPORTS_NON_INTERACTIVE

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /clear command.

        Clear the conversation history and free up context window space.
        Delegates to the conversation-clearing implementation.
        """
        from claude_code.commands.clear.clear import call as _call  # type: ignore[import]

        return await _call(args=args, context=context)


default = ClearCommand()

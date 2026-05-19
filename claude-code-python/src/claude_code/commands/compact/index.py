"""Compact command descriptor. Ported from commands/compact/index.ts"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Literal, Optional


NAME = "compact"
DESCRIPTION = (
    "Clear conversation history but keep a summary in context. "
    "Optional: /compact [instructions for summarization]"
)
ARGUMENT_HINT: str = "<optional custom summarization instructions>"
TYPE: Literal["local"] = "local"
SUPPORTS_NON_INTERACTIVE: bool = True


def is_enabled() -> bool:
    """Return False when the DISABLE_COMPACT environment variable is set."""
    val = os.environ.get("DISABLE_COMPACT", "").lower()
    return val not in ("1", "true", "yes", "on")


@dataclass
class CompactCommand:
    """Descriptor for the /compact slash command."""

    type: str = TYPE
    name: str = NAME
    description: str = DESCRIPTION
    argument_hint: str = ARGUMENT_HINT
    supports_non_interactive: bool = SUPPORTS_NON_INTERACTIVE

    def is_enabled(self) -> bool:  # noqa: D102
        return is_enabled()

    async def call(self, args: str = "", context=None) -> dict:
        """Handle /compact command.

        Summarize and compact the conversation history, optionally using
        custom summarization instructions supplied via *args*.
        """
        from claude_code.commands.compact.compact import call as _call  # type: ignore[import]

        result = await _call(args=args, context=context)
        if hasattr(result, "__dict__"):
            return result.__dict__
        return result  # type: ignore[return-value]


default = CompactCommand()

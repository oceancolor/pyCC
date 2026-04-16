"""Conversation clearing utility. Ported from commands/clear/conversation.ts"""
from __future__ import annotations
from typing import Any, Optional

async def clear_conversation(context: Any = None) -> None:
    """Clear conversation, generate new session ID, run end/start hooks."""
    if context:
        reset_fn = getattr(context, "set_messages", None)
        if reset_fn:
            reset_fn([])

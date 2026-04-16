"""
/clear command — Clear conversation history and reset session
原始 TS: src/commands/clear/

Usage: /clear
Aliases: /reset, /new
"""
from __future__ import annotations

from typing import Any, Optional


def clear_command(session: Any) -> str:
    """
    Clear conversation history and reset the session.

    Args:
        session: The current session object. Expected to have:
            - messages: list of conversation messages
            - usage: optional usage/cost tracker
            - turn_count: optional turn counter

    Returns:
        A confirmation message string.
    """
    cleared_count = 0

    # Clear message history
    if hasattr(session, "messages") and isinstance(session.messages, list):
        cleared_count = len(session.messages)
        session.messages.clear()

    # Reset turn count if tracked
    if hasattr(session, "turn_count"):
        session.turn_count = 0

    # Reset usage stats if tracked
    if hasattr(session, "usage") and session.usage is not None:
        if isinstance(session.usage, dict):
            session.usage.clear()
        elif hasattr(session.usage, "reset"):
            session.usage.reset()

    # Reset cost tracker if tracked separately
    if hasattr(session, "cost_tracker") and session.cost_tracker is not None:
        if hasattr(session.cost_tracker, "reset"):
            session.cost_tracker.reset()
        elif isinstance(session.cost_tracker, dict):
            session.cost_tracker.clear()

    if cleared_count:
        return f"✓ Cleared {cleared_count} messages. Conversation history reset."
    else:
        return "✓ Conversation history cleared."

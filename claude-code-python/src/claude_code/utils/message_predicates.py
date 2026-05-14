"""Message type predicates. Ported from messagePredicates.ts.

tool_result messages share type:'user' with human turns; the discriminant is
the optional tool_use_result field.  Four PRs (#23977, #24016, #24022,
#24025) independently fixed miscounts from checking type==='user' alone.
"""
from __future__ import annotations

from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    pass

__all__ = [
    "is_human_turn",
    "is_tool_result",
    "is_assistant_turn",
    "is_system_message",
    "is_meta_message",
]


def is_human_turn(m: Any) -> bool:
    """Return True if *m* is a genuine human-turn message (not a tool result).

    Checks:
    - type == 'user'
    - not a meta message (is_meta is not truthy)
    - no tool_use_result (discriminates from tool-result pseudo-user messages)
    """
    return (
        getattr(m, "type", None) == "user"
        and not getattr(m, "is_meta", False)
        and getattr(m, "tool_use_result", None) is None
    )


def is_tool_result(m: Any) -> bool:
    """Return True if *m* is a tool-use result wrapped as a user message."""
    return (
        getattr(m, "type", None) == "user"
        and getattr(m, "tool_use_result", None) is not None
    )


def is_assistant_turn(m: Any) -> bool:
    """Return True if *m* is an assistant-turn message."""
    return getattr(m, "type", None) == "assistant"


def is_system_message(m: Any) -> bool:
    """Return True if *m* is a system message."""
    return getattr(m, "type", None) == "system"


def is_meta_message(m: Any) -> bool:
    """Return True if *m* is a meta / synthetic message (not from the model or user)."""
    return bool(getattr(m, "is_meta", False))


def get_message_role(m: Any) -> str:
    """Return the effective role of *m* as a string."""
    if is_meta_message(m):
        return "meta"
    msg_type = getattr(m, "type", None)
    if msg_type == "user":
        return "tool_result" if is_tool_result(m) else "user"
    return str(msg_type) if msg_type else "unknown"

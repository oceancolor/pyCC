"""Message type predicates. Ported from utils/messagePredicates.ts

tool_result messages share type='user' with human turns; the discriminant
is the optional toolUseResult field. Four PRs independently fixed miscounts
from checking type==='user' alone.
"""

from __future__ import annotations

from typing import Any, Dict


def is_human_turn(m: Any) -> bool:
    """Return True if *m* is a human (non-tool-result, non-meta) user message.

    Checks:
    1. ``type == 'user'``
    2. ``is_meta`` is falsy
    3. ``tool_use_result`` is None / absent
    """
    if isinstance(m, dict):
        return (
            m.get("type") == "user"
            and not m.get("isMeta", False)
            and not m.get("is_meta", False)
            and m.get("toolUseResult") is None
            and m.get("tool_use_result") is None
        )
    return (
        getattr(m, "type", None) == "user"
        and not getattr(m, "is_meta", False)
        and not getattr(m, "isMeta", False)
        and getattr(m, "tool_use_result", None) is None
        and getattr(m, "toolUseResult", None) is None
    )


def is_assistant_turn(m: Any) -> bool:
    """Return True if *m* is an assistant message."""
    if isinstance(m, dict):
        return m.get("type") == "assistant"
    return getattr(m, "type", None) == "assistant"


def is_tool_use_message(m: Any) -> bool:
    """Return True if *m* is a tool-use (assistant-side) message."""
    if isinstance(m, dict):
        content = m.get("content", [])
    else:
        content = getattr(m, "content", [])
    if isinstance(content, list):
        return any(
            (isinstance(b, dict) and b.get("type") == "tool_use")
            or (hasattr(b, "type") and getattr(b, "type") == "tool_use")
            for b in content
        )
    return False


def is_tool_result_message(m: Any) -> bool:
    """Return True if *m* is a tool-result (user-side) message.

    These share ``type='user'`` with human turns but include ``toolUseResult``.
    """
    if isinstance(m, dict):
        return m.get("type") == "user" and (
            m.get("toolUseResult") is not None
            or m.get("tool_use_result") is not None
        )
    return getattr(m, "type", None) == "user" and (
        getattr(m, "tool_use_result", None) is not None
        or getattr(m, "toolUseResult", None) is not None
    )


def is_meta_message(m: Any) -> bool:
    """Return True if *m* is an internal meta-message."""
    if isinstance(m, dict):
        return bool(m.get("isMeta") or m.get("is_meta"))
    return bool(getattr(m, "isMeta", False) or getattr(m, "is_meta", False))

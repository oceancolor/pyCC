"""
Group messages by API round boundaries.
Ported from services/compact/grouping.ts

Groups messages at API-round boundaries: one group per API round-trip.
A boundary fires when a NEW assistant response begins (different
message.id from the prior assistant).
"""
from __future__ import annotations

from typing import Dict, List, Optional


def group_messages_by_api_round(messages: List[Dict]) -> List[List[Dict]]:
    """Group messages by API round boundaries.

    Groups consecutive messages that belong to the same API round-trip.
    A new group starts when a new assistant response begins (detected by
    a different ``message.id`` on the assistant message).

    Replaces prior human-turn grouping with finer-grained API-round grouping,
    allowing reactive compact to operate on single-prompt agentic sessions
    (SDK/CCR/eval callers) where the entire workload is one human turn.

    Args:
        messages: Flat list of normalized messages.

    Returns:
        List of groups, where each group is a list of messages.
    """
    groups: List[List[Dict]] = []
    current: List[Dict] = []
    last_assistant_id: Optional[str] = None

    for msg in messages:
        if (
            msg.get("type") == "assistant"
            and msg.get("message", {}).get("id") != last_assistant_id
            and current
        ):
            groups.append(current)
            current = [msg]
        else:
            current.append(msg)

        if msg.get("type") == "assistant":
            last_assistant_id = msg.get("message", {}).get("id")

    if current:
        groups.append(current)

    return groups

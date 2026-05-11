"""Shared tool utilities. Ported from tools/utils.ts"""
from __future__ import annotations
from typing import Any, Dict, List, Optional


def tag_messages_with_tool_use_id(
    messages: List[Dict[str, Any]],
    tool_use_id: Optional[str],
) -> List[Dict[str, Any]]:
    """Tag user messages with a sourceToolUseID so they stay transient until the tool resolves.

    This prevents the "is running" message from being duplicated in the UI.
    Ported from tools/utils.ts: tagMessagesWithToolUseID.
    """
    if not tool_use_id:
        return messages

    result = []
    for msg in messages:
        if isinstance(msg, dict) and msg.get("type") == "user":
            msg = {**msg, "sourceToolUseID": tool_use_id}
        result.append(msg)
    return result


def get_tool_use_id_from_parent_message(
    parent_message: Dict[str, Any],
    tool_name: str,
) -> Optional[str]:
    """Extract the tool_use_id for a given tool name from a parent assistant message.

    Ported from tools/utils.ts: getToolUseIDFromParentMessage.
    """
    content = (
        parent_message.get("message", {}).get("content", [])
        if isinstance(parent_message, dict)
        else []
    )
    for block in content:
        if (
            isinstance(block, dict)
            and block.get("type") == "tool_use"
            and block.get("name") == tool_name
        ):
            return block.get("id")
    return None


# Convenience helpers that pre-date the utils.ts port and are used internally.

def get_tool_by_name(tools: List[Any], name: str) -> Optional[Any]:
    """Return the first tool in *tools* whose .name matches *name*, or None."""
    for t in tools:
        if getattr(t, "name", None) == name:
            return t
    return None


def tool_matches_name(tool: Any, name: str) -> bool:
    """Return True if *tool*.name equals *name*."""
    return getattr(tool, "name", None) == name

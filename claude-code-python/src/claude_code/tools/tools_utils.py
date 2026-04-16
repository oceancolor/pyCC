"""Tool utility functions. Ported from tools/utils.ts"""
from __future__ import annotations
from typing import Any, List, Optional


def tag_messages_with_tool_use_id(messages: List[dict], tool_use_id: Optional[str]) -> List[dict]:
    """Tag user messages with a sourceToolUseID so they stay transient until the tool resolves."""
    if not tool_use_id:
        return messages
    result = []
    for m in messages:
        if m.get("type") == "user":
            result.append({**m, "sourceToolUseID": tool_use_id})
        else:
            result.append(m)
    return result


def get_tool_use_id_from_parent_message(parent_message: dict, tool_name: str) -> Optional[str]:
    """Extract the tool use ID from a parent message for a given tool name."""
    content = parent_message.get("message", {}).get("content", [])
    for block in content:
        if block.get("type") == "tool_use" and block.get("name") == tool_name:
            return block.get("id")
    return None

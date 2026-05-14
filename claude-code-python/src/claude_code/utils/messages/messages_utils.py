"""Message utilities. Ported from utils/messages/."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence


def get_message_text(message: dict) -> str:
    """Extract the plain text from a message dict.

    Handles both string content and list-of-content-blocks formats.
    """
    content = message.get("message", {}).get("content", "") or message.get("content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content) if content else ""


def get_message_role(message: dict) -> str:
    """Return the role of a message ('assistant', 'user', 'system')."""
    # Top-level type field
    t = message.get("type", "")
    if t in ("assistant", "user", "system"):
        return t
    # Nested .message.role
    return message.get("message", {}).get("role", "unknown")


def is_assistant_message(message: dict) -> bool:
    """Return True if the message is from the assistant."""
    return get_message_role(message) == "assistant"


def is_user_message(message: dict) -> bool:
    """Return True if the message is from the user."""
    return get_message_role(message) == "user"


def is_tool_use_block(block: dict) -> bool:
    """Return True if the given content block is a tool_use block."""
    return isinstance(block, dict) and block.get("type") == "tool_use"


def is_tool_result_block(block: dict) -> bool:
    """Return True if the given content block is a tool_result block."""
    return isinstance(block, dict) and block.get("type") == "tool_result"


def get_content_blocks(message: dict) -> List[dict]:
    """Return the list of content blocks from a message, or an empty list."""
    content = message.get("message", {}).get("content") or message.get("content", [])
    if isinstance(content, list):
        return [b for b in content if isinstance(b, dict)]
    return []


def get_tool_uses(message: dict) -> List[dict]:
    """Return all tool_use blocks from a message."""
    return [b for b in get_content_blocks(message) if is_tool_use_block(b)]


def get_tool_results(message: dict) -> List[dict]:
    """Return all tool_result blocks from a message."""
    return [b for b in get_content_blocks(message) if is_tool_result_block(b)]


def count_tool_uses(messages: Sequence[dict]) -> int:
    """Count total tool_use blocks across a list of messages."""
    return sum(len(get_tool_uses(m)) for m in messages)


def truncate_message_list(
    messages: List[dict],
    max_messages: int,
) -> List[dict]:
    """Return the last ``max_messages`` messages from the list."""
    if len(messages) <= max_messages:
        return messages
    return messages[-max_messages:]

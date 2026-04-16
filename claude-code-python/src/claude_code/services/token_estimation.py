"""
Token estimation service
原始 TS: src/services/tokenEstimation.ts
"""
from __future__ import annotations

from typing import Any, Optional


def estimate_tokens_from_string(text: str) -> int:
    """
    Rough token estimation: ~4 chars per token.
    原始 TS: estimateTokensFromString

    NOTE: For accurate counts, use the Anthropic API's token counting endpoint.
    """
    return max(1, len(text) // 4)


def estimate_tokens_from_content(content: Any) -> int:
    """
    Estimate tokens from message content (string or content blocks).
    """
    if isinstance(content, str):
        return estimate_tokens_from_string(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    total += estimate_tokens_from_string(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    total += estimate_tokens_from_string(str(block.get("input", "")))
                elif block.get("type") == "tool_result":
                    c = block.get("content", "")
                    if isinstance(c, str):
                        total += estimate_tokens_from_string(c)
                    elif isinstance(c, list):
                        total += estimate_tokens_from_content(c)
            elif hasattr(block, "text"):
                total += estimate_tokens_from_string(block.text)
        return total
    return 0


def estimate_messages_tokens(messages: list[dict[str, Any]]) -> int:
    """Estimate total tokens across all messages."""
    total = 0
    for msg in messages:
        total += estimate_tokens_from_content(msg.get("content", ""))
    # Add overhead per message (role, structure)
    total += len(messages) * 4
    return total

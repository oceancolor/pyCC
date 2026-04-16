"""Agent task summary generation. Ported from services/AgentSummary/agentSummary.ts (179L)"""
from __future__ import annotations
from typing import Any, List, Optional


async def generate_agent_summary(
    messages: List[Any],
    task_description: str,
    model: Optional[str] = None,
) -> str:
    """Generate a concise summary of what the agent accomplished."""
    # Collect text content from assistant messages
    text_blocks = []
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        content = msg.get("content", [])
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text_blocks.append(block.get("text", ""))

    if not text_blocks:
        return f"Completed: {task_description}"

    # Return last meaningful assistant message as summary
    for text in reversed(text_blocks):
        stripped = text.strip()
        if stripped and len(stripped) > 10:
            return stripped[:500]

    return f"Completed: {task_description}"

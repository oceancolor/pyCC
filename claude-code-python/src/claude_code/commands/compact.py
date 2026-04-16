# 原始 TS: commands/compact/index.ts + compact.ts
"""Compact command - compress conversation history to save context."""
from __future__ import annotations

import logging
from typing import Any

from ..services.compact import CompactOptions, compact_messages

logger = logging.getLogger(__name__)


async def run(args: str = "", context: Any = None) -> dict[str, Any]:
    """Compact the current conversation.

    Optional *args* may contain custom summarisation instructions.
    """
    instructions = args.strip()
    messages: list[dict[str, Any]] = []

    if context and hasattr(context, "messages"):
        messages = list(context.messages)

    if not messages:
        return {"type": "text", "value": "Nothing to compact — conversation is empty."}

    opts = CompactOptions(custom_instructions=instructions)
    result = await compact_messages(messages, opts)

    logger.info(
        "Compact: %d messages → 1 summary (%s)",
        result.original_message_count,
        result.summary[:60],
    )

    return {
        "type": "compact",
        "summary": result.summary,
        "original_count": result.original_message_count,
    }

# 原始 TS: services/awaySummary.ts
"""Away-summary service.

Generates a short recap for the "while you were away" card when the user
returns to a long-running session.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Only use the most recent N messages to avoid "prompt too long" errors
RECENT_MESSAGE_WINDOW = 30


def _build_prompt(memory: str | None) -> str:
    memory_block = f"Session memory (broader context):\n{memory}\n\n" if memory else ""
    return (
        f"{memory_block}"
        "The user stepped away and is coming back. Write exactly 1-3 short sentences. "
        "Start by stating the high-level task — what they are building or debugging, "
        "not implementation details. Next: the concrete next step. "
        "Skip status reports and commit recaps."
    )


async def generate_away_summary(
    messages: list[dict[str, Any]],
    signal: Any | None = None,
) -> str | None:
    """Return a 1-3 sentence recap, or None if unavailable.

    TODO: Call queryModelWithoutStreaming with the small/fast model.
    """
    if not messages:
        return None

    recent = messages[-RECENT_MESSAGE_WINDOW:]
    # TODO: fetch session memory and call model
    logger.debug("generate_away_summary: %d messages (stub)", len(recent))
    return None

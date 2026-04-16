"""
Side question ("/btw") feature – lightweight one-shot queries that do not
interrupt or enter the main conversation context.
Ported from sideQuestion.ts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Constants / patterns
# ---------------------------------------------------------------------------

# Matches "/btw" at the start of a message (case-insensitive, word boundary)
_BTW_PATTERN = re.compile(r"^/btw\b", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class SideQuestionResult:
    response: Optional[str]
    usage: dict[str, Any]


# ---------------------------------------------------------------------------
# Trigger position helpers
# ---------------------------------------------------------------------------

def find_btw_trigger_positions(text: str) -> list[dict[str, Any]]:
    """
    Find positions of the '/btw' keyword at the start of text.

    Returns a list of dicts with keys: word, start, end.
    """
    positions: list[dict[str, Any]] = []
    # Re-create the pattern to avoid shared lastIndex issues (mirrors TS comment)
    for match in re.finditer(r"^/btw\b", text, re.IGNORECASE):
        positions.append(
            {
                "word": match.group(0),
                "start": match.start(),
                "end": match.end(),
            }
        )
    return positions


def is_side_question(text: str) -> bool:
    """Return True if the text starts with the /btw trigger."""
    return bool(_BTW_PATTERN.match(text.strip()))


def strip_btw_prefix(text: str) -> str:
    """Remove the leading /btw prefix (and surrounding whitespace) from text."""
    return _BTW_PATTERN.sub("", text).strip()


# ---------------------------------------------------------------------------
# Side-question runner (async stub – full impl requires API/agent layer)
# ---------------------------------------------------------------------------

async def ask_side_question(
    question: str,
    context: Optional[str] = None,
    *,
    cache_safe_params: Optional[dict[str, Any]] = None,
) -> SideQuestionResult:
    """
    Run a side question without entering the main conversation.

    This is a stub implementation. In the full system this forks an agent
    that shares the parent's prompt cache but discards its messages afterwards.

    Args:
        question: The question to ask.
        context: Optional extra context string to prepend.
        cache_safe_params: Optional API params for cache reuse.

    Returns:
        SideQuestionResult with response text and token usage.
    """
    # Build the wrapped prompt (mirrors the TS system-reminder wrapper)
    wrapped = (
        "<system-reminder>This is a side question. Answer directly in a single "
        "response. You have NO tools available. This is a one-off response.</system-reminder>\n\n"
    )
    if context:
        wrapped += f"Context: {context}\n\n"
    wrapped += question

    # Stub: return a placeholder indicating the forked-agent layer is needed.
    # Replace with actual forked-agent invocation when the API layer is wired up.
    return SideQuestionResult(
        response=(
            "(Side question stub: forked agent not available in this environment. "
            f"Question received: {question!r})"
        ),
        usage={"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0},
    )


def extract_side_question_response(messages: list[dict[str, Any]]) -> Optional[str]:
    """
    Extract the display string from a list of forked-agent messages.

    Handles adaptive thinking (thinking block arrives before text block),
    tool-use fallback, and API error surfacing.
    """
    # Flatten all assistant content blocks across per-block messages
    assistant_blocks: list[dict[str, Any]] = []
    for msg in messages:
        if msg.get("type") == "assistant":
            content = msg.get("message", {}).get("content", [])
            if isinstance(content, list):
                assistant_blocks.extend(content)

    if assistant_blocks:
        # Concatenate all text blocks
        text_parts = [
            b.get("text", "")
            for b in assistant_blocks
            if b.get("type") == "text"
        ]
        text = "\n\n".join(p for p in text_parts if p).strip()
        if text:
            return text

        # Model tried to call a tool despite instructions
        tool_block = next(
            (b for b in assistant_blocks if b.get("type") == "tool_use"), None
        )
        if tool_block:
            tool_name = tool_block.get("name", "a tool")
            return (
                f"(The model tried to call {tool_name} instead of answering directly. "
                "Try rephrasing or ask in the main conversation.)"
            )

    # No assistant content – surface any API error message
    for msg in messages:
        if msg.get("type") == "system" and msg.get("subtype") == "api_error":
            error = msg.get("error", {})
            error_msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
            return f"(API error: {error_msg})"

    return None

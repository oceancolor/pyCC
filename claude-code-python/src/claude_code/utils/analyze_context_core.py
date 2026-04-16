"""
Context analysis core — Python equivalent of analyzeContext.ts (data structures
and token-counting logic only; UI rendering parts are omitted).

Token estimation uses a simple approximation (chars / 4) matching the
roughTokenCountEstimation heuristic from the TypeScript source.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional, Union


# ---------------------------------------------------------------------------
# Token estimation helper
# ---------------------------------------------------------------------------

def _rough_token_count(text: str) -> int:
    """Estimate token count: ~4 chars per token (GPT/Claude heuristic)."""
    return max(1, len(text) // 4)


def _serialize(obj: Any) -> str:
    """JSON-serialize an object for token estimation."""
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class ContextAnalysis:
    """
    Aggregated token breakdown for a conversation's context window.

    Attributes
    ----------
    total_tokens:
        Estimated total tokens across all messages.
    tool_results_tokens:
        Tokens consumed by tool_result blocks (user-role messages).
    tool_calls_tokens:
        Tokens consumed by tool_use blocks (assistant-role messages).
    user_messages_tokens:
        Tokens consumed by plain user text (excludes tool results).
    assistant_tokens:
        Tokens consumed by plain assistant text (excludes tool calls).
    attachment_tokens:
        Tokens from attachment-type messages.
    message_count:
        Total number of messages analysed.
    """

    total_tokens: int = 0
    tool_results_tokens: int = 0
    tool_calls_tokens: int = 0
    user_messages_tokens: int = 0
    assistant_tokens: int = 0
    attachment_tokens: int = 0
    message_count: int = 0


# ---------------------------------------------------------------------------
# Message-type aliases
# ---------------------------------------------------------------------------

# A "message" here is a dict with at minimum:
#   {"type": "user"|"assistant"|"attachment", "message": {...}}
# or just the raw Anthropic SDK dict:
#   {"role": "user"|"assistant", "content": ...}
Message = dict[str, Any]


# ---------------------------------------------------------------------------
# Internal processors
# ---------------------------------------------------------------------------

def _process_assistant_message(msg: Message, analysis: ContextAnalysis) -> None:
    """Extract token counts from an assistant-role message."""
    inner = msg.get("message", msg)
    content = inner.get("content", "")

    if isinstance(content, str):
        analysis.assistant_tokens += _rough_token_count(content)
        return

    for block in content:
        block_tokens = _rough_token_count(_serialize(block))
        if isinstance(block, dict) and block.get("type") == "tool_use":
            analysis.tool_calls_tokens += block_tokens
        else:
            analysis.assistant_tokens += block_tokens


def _process_user_message(msg: Message, analysis: ContextAnalysis) -> None:
    """Extract token counts from a user-role message."""
    inner = msg.get("message", msg)
    content = inner.get("content", "")

    if isinstance(content, str):
        analysis.user_messages_tokens += _rough_token_count(content)
        return

    for block in content:
        block_tokens = _rough_token_count(_serialize(block))
        if isinstance(block, dict) and block.get("type") == "tool_result":
            analysis.tool_results_tokens += block_tokens
        else:
            analysis.user_messages_tokens += block_tokens


def _process_attachment(msg: Message, analysis: ContextAnalysis) -> None:
    """Extract token counts from an attachment message."""
    attachment = msg.get("attachment", msg.get("message", msg))
    tokens = _rough_token_count(_serialize(attachment))
    analysis.attachment_tokens += tokens


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def analyze_context(messages: list[Message]) -> ContextAnalysis:
    """
    Analyse a list of conversation messages and return token breakdowns.

    Parameters
    ----------
    messages:
        List of message dicts.  Each dict should have a ``"type"`` key of
        ``"user"``, ``"assistant"``, or ``"attachment"``.  Raw Anthropic
        SDK dicts with ``"role"`` keys are also accepted.

    Returns
    -------
    ContextAnalysis
        Populated token breakdown.
    """
    analysis = ContextAnalysis(message_count=len(messages))

    for msg in messages:
        msg_type = msg.get("type") or msg.get("role", "")

        if msg_type == "assistant":
            _process_assistant_message(msg, analysis)
        elif msg_type == "user":
            _process_user_message(msg, analysis)
        elif msg_type == "attachment":
            _process_attachment(msg, analysis)
        else:
            # Unknown type — count whole block against total
            analysis.user_messages_tokens += _rough_token_count(_serialize(msg))

    analysis.total_tokens = (
        analysis.tool_results_tokens
        + analysis.tool_calls_tokens
        + analysis.user_messages_tokens
        + analysis.assistant_tokens
        + analysis.attachment_tokens
    )

    return analysis


def get_context_summary(analysis: ContextAnalysis) -> str:
    """
    Return a human-readable summary of the context analysis.

    Parameters
    ----------
    analysis:
        Result from :func:`analyze_context`.

    Returns
    -------
    str
        Multi-line summary string.
    """
    total = analysis.total_tokens or 1  # avoid div-by-zero

    def pct(n: int) -> str:
        return f"{n / total * 100:.1f}%"

    lines = [
        f"Context Analysis ({analysis.message_count} messages)",
        f"  Total tokens   : {analysis.total_tokens:,}",
        f"  Assistant text : {analysis.assistant_tokens:,}  ({pct(analysis.assistant_tokens)})",
        f"  Tool calls     : {analysis.tool_calls_tokens:,}  ({pct(analysis.tool_calls_tokens)})",
        f"  User messages  : {analysis.user_messages_tokens:,}  ({pct(analysis.user_messages_tokens)})",
        f"  Tool results   : {analysis.tool_results_tokens:,}  ({pct(analysis.tool_results_tokens)})",
        f"  Attachments    : {analysis.attachment_tokens:,}  ({pct(analysis.attachment_tokens)})",
    ]
    return "\n".join(lines)

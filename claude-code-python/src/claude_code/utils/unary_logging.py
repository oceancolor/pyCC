"""Unary event logging. Ported from unaryLogging.ts.

Logs events for the unary (single-shot, non-streaming) interaction flow
such as tool use, str_replace and file write completions.  The TypeScript
source calls into the analytics pipeline; here we delegate to the sinks
module so the same events are routed to whatever backend is configured.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Literal, Optional, Union

__all__ = [
    "CompletionType",
    "UnaryLogEvent",
    "log_unary_event",
    "log_unary_event_sync",
]

logger = logging.getLogger(__name__)

CompletionType = Literal[
    "str_replace_single",
    "str_replace_multi",
    "write_file_single",
    "tool_use_single",
]


@dataclass
class UnaryLogEvent:
    """Payload for a single unary interaction event."""

    completion_type: CompletionType
    """The kind of completion that generated this event."""

    event: Literal["accept", "reject", "response"]
    """Whether the user accepted, rejected, or the model responded."""

    language_name: str
    """Programming language of the file being edited (e.g. 'python')."""

    message_id: str
    """The assistant message ID this event is associated with."""

    platform: str
    """OS/platform identifier (e.g. 'linux', 'darwin', 'win32')."""

    has_feedback: bool = False
    """Whether the user provided explicit feedback."""

    extra: dict = field(default_factory=dict)
    """Additional key/value pairs to include in the event payload."""


def _emit(event: UnaryLogEvent) -> None:
    """Internal: dispatch the event to analytics sinks."""
    try:
        from claude_code.utils.sinks import emit_analytics_event

        payload = {
            "completion_type": event.completion_type,
            "event": event.event,
            "language_name": event.language_name,
            "message_id": event.message_id,
            "platform": event.platform,
            **event.extra,
        }
        if event.has_feedback:
            payload["hasFeedback"] = True
        emit_analytics_event("tengu_unary_event", payload)
    except Exception as exc:
        logger.debug("log_unary_event: analytics emit failed: %s", exc)


async def log_unary_event(event: UnaryLogEvent) -> None:
    """Asynchronously log a unary interaction event.

    Runs the synchronous emit in the default executor to avoid blocking
    an asyncio event loop.
    """
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _emit, event)


def log_unary_event_sync(event: UnaryLogEvent) -> None:
    """Synchronously log a unary interaction event."""
    _emit(event)

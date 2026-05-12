"""
Analytics service — public API for event logging.
Ported from services/analytics/index.ts

Provides logEvent / logEventAsync with a sink model. Events are queued
until a sink is attached via attachAnalyticsSink().
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Coroutine, Dict, List, Optional, Protocol

log = logging.getLogger(__name__)

LogEventMetadata = Dict[str, Any]


class AnalyticsSink(Protocol):
    """Protocol for analytics sinks attached at startup."""

    def log_event(self, event_name: str, metadata: LogEventMetadata) -> None: ...

    async def log_event_async(
        self, event_name: str, metadata: LogEventMetadata
    ) -> None: ...


class _QueuedEvent:
    __slots__ = ("event_name", "metadata", "is_async")

    def __init__(self, event_name: str, metadata: LogEventMetadata, *, is_async: bool) -> None:
        self.event_name = event_name
        self.metadata = metadata
        self.is_async = is_async


# Module-level sink (None until attached)
_sink: Optional[AnalyticsSink] = None

# Event queue for events logged before sink is attached
_event_queue: List[_QueuedEvent] = []


def attach_analytics_sink(new_sink: AnalyticsSink) -> None:
    """Attach the analytics sink that will receive all events.

    Idempotent — if a sink is already attached this is a no-op.
    Queued events are drained after attachment.
    """
    global _sink
    if _sink is not None:
        return

    _sink = new_sink

    if _event_queue:
        queued = list(_event_queue)
        _event_queue.clear()

        # Drain synchronous events immediately; schedule async events
        loop: Optional[asyncio.AbstractEventLoop] = None
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            pass

        for event in queued:
            if event.is_async and loop is not None and not loop.is_closed():
                loop.call_soon(
                    lambda e=event: asyncio.ensure_future(
                        _sink.log_event_async(e.event_name, e.metadata)  # type: ignore[union-attr]
                    )
                )
            else:
                try:
                    _sink.log_event(event.event_name, event.metadata)
                except Exception as exc:
                    log.debug("analytics drain error: %s", exc)


def log_event(event_name: str, metadata: LogEventMetadata) -> None:
    """Log an event to analytics backends (synchronous).

    If no sink is attached, the event is queued for later delivery.
    """
    if _sink is None:
        _event_queue.append(_QueuedEvent(event_name, metadata, is_async=False))
        return
    try:
        _sink.log_event(event_name, metadata)
    except Exception as exc:
        log.debug("log_event error: %s", exc)


async def log_event_async(event_name: str, metadata: LogEventMetadata) -> None:
    """Log an event to analytics backends (asynchronous).

    If no sink is attached, the event is queued for later delivery.
    """
    if _sink is None:
        _event_queue.append(_QueuedEvent(event_name, metadata, is_async=True))
        return
    try:
        await _sink.log_event_async(event_name, metadata)
    except Exception as exc:
        log.debug("log_event_async error: %s", exc)


def _reset_for_testing() -> None:
    """Reset analytics state for testing purposes."""
    global _sink
    _sink = None
    _event_queue.clear()

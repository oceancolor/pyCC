# 原始 TS: services/analytics/index.ts + sink.ts
"""Analytics service - event logging stub.

Events are queued until a sink is attached during app initialization.
All sensitive data (code, file paths) must be explicitly verified before logging.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

# Type alias for verified-safe analytics metadata (not code/file paths)
AnalyticsMetadata = str  # In TS this is a nominal/branded type

# --- Internal queue ---
_event_queue: list[tuple[str, dict[str, Any]]] = []
_sink: Callable[[str, dict[str, Any]], None] | None = None


def log_event(event_name: str, metadata: dict[str, Any] | None = None) -> None:
    """Queue or emit an analytics event."""
    payload = metadata or {}
    if _sink is not None:
        try:
            _sink(event_name, payload)
        except Exception:  # noqa: BLE001
            logger.debug("Analytics sink error for event: %s", event_name)
    else:
        _event_queue.append((event_name, payload))


def attach_analytics_sink(sink: Callable[[str, dict[str, Any]], None]) -> None:
    """Attach a sink and flush the queue. Called during app init."""
    global _sink  # noqa: PLW0603
    _sink = sink
    while _event_queue:
        name, payload = _event_queue.pop(0)
        try:
            sink(name, payload)
        except Exception:  # noqa: BLE001
            pass


def strip_proto_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    """Remove _PROTO_* keys before sending to general-access storage.

    These keys hold PII-tagged values destined for privileged BQ columns.
    Any non-1P sink must call this before fanout.
    """
    has_proto = any(k.startswith("_PROTO_") for k in metadata)
    if not has_proto:
        return metadata
    return {k: v for k, v in metadata.items() if not k.startswith("_PROTO_")}


def detach_sink() -> None:
    """Remove the current sink (mainly for testing)."""
    global _sink  # noqa: PLW0603
    _sink = None

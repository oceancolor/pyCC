"""Analytics sink implementation. Ported from services/analytics/sink.ts

Routes events to Datadog and 1P event logging.
Call initialize_analytics_sink() during app startup to attach the sink.
"""
from __future__ import annotations
from typing import Any, Dict, Optional

# Module-level gate state; starts None, initialized during startup
_is_datadog_gate_enabled: Optional[bool] = None

_DATADOG_GATE_NAME = "tengu_log_datadog_events"


def _should_track_datadog() -> bool:
    """Check if Datadog tracking is enabled. Falls back to cached value."""
    try:
        from claude_code.services.analytics.sink_killswitch import is_sink_killed
        if is_sink_killed("datadog"):
            return False
    except Exception:
        return False

    if _is_datadog_gate_enabled is not None:
        return _is_datadog_gate_enabled

    try:
        from claude_code.services.analytics.growthbook import check_statsig_feature_gate_cached_may_be_stale
        return check_statsig_feature_gate_cached_may_be_stale(_DATADOG_GATE_NAME)
    except Exception:
        return False


def _log_event_impl(event_name: str, metadata: Dict[str, Any]) -> None:
    """Synchronous event logging implementation."""
    try:
        from claude_code.services.analytics.first_party_event_logger import should_sample_event
        sample_result = should_sample_event(event_name)
    except Exception:
        sample_result = None

    # Drop if sampled out
    if sample_result == 0:
        return

    metadata_with_sample = (
        {**metadata, "sample_rate": sample_result}
        if sample_result is not None
        else metadata
    )

    if _should_track_datadog():
        try:
            from claude_code.services.analytics.datadog import track_datadog_event
            from claude_code.services.analytics.index import strip_proto_fields
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(track_datadog_event(event_name, strip_proto_fields(metadata_with_sample)))
        except Exception:
            pass

    try:
        from claude_code.services.analytics.first_party_event_logger import log_event_to_1p
        log_event_to_1p(event_name, metadata_with_sample)
    except Exception:
        pass


async def _log_event_async_impl(event_name: str, metadata: Dict[str, Any]) -> None:
    """Asynchronous event logging (wraps sync impl)."""
    _log_event_impl(event_name, metadata)


def initialize_analytics_gates() -> None:
    """Initialize analytics gates during startup. Updates from cached server values."""
    global _is_datadog_gate_enabled
    try:
        from claude_code.services.analytics.growthbook import check_statsig_feature_gate_cached_may_be_stale
        _is_datadog_gate_enabled = check_statsig_feature_gate_cached_may_be_stale(_DATADOG_GATE_NAME)
    except Exception:
        _is_datadog_gate_enabled = False


def initialize_analytics_sink() -> None:
    """Initialize the analytics sink. Idempotent; safe to call multiple times."""
    try:
        from claude_code.services.analytics.index import attach_analytics_sink
        attach_analytics_sink({
            "logEvent": _log_event_impl,
            "logEventAsync": _log_event_async_impl,
        })
    except Exception:
        pass

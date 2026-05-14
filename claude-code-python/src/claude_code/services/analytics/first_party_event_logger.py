"""First-party event logger. Ported from services/analytics/firstPartyEventLogger.ts"""
from __future__ import annotations
import os
from typing import Any, Dict, Optional

# Module-level state
_first_party_event_logger_initialized: bool = False


def should_sample_event(event_name: str) -> Optional[float]:
    """Determine if an event should be sampled.

    Returns sample_rate if event should be logged, None if no sampling needed,
    0 if event should be dropped.
    """
    try:
        from claude_code.services.analytics.growthbook import get_dynamic_config_cached_may_be_stale
        config: Dict[str, Any] = get_dynamic_config_cached_may_be_stale("tengu_event_sampling_config", {})
    except Exception:
        return None

    event_config = config.get(event_name)
    if not event_config:
        return None

    sample_rate = event_config.get("sample_rate")
    if not isinstance(sample_rate, (int, float)) or sample_rate < 0 or sample_rate > 1:
        return None

    if sample_rate >= 1:
        return None

    if sample_rate <= 0:
        return 0

    import random
    return sample_rate if random.random() < sample_rate else 0


def is_1p_event_logging_enabled() -> bool:
    """Check if 1P event logging is enabled."""
    from claude_code.services.analytics.config import is_analytics_disabled
    return not is_analytics_disabled()


def log_event_to_1p(
    event_name: str,
    metadata: Dict[str, Any] = None,  # type: ignore[assignment]
) -> None:
    """Log a 1st-party event for internal analytics (fire-and-forget)."""
    if metadata is None:
        metadata = {}

    if not is_1p_event_logging_enabled():
        return

    try:
        from claude_code.services.analytics.sink_killswitch import is_sink_killed
        if is_sink_killed("firstParty"):
            return
    except Exception:
        pass

    if os.environ.get("USER_TYPE") == "ant":
        try:
            from claude_code.utils.debug import log_for_debugging
            import json
            log_for_debugging(f"[ANT-ONLY] 1P event: {event_name} {json.dumps(metadata, default=str)}")
        except Exception:
            pass


def initialize_1p_event_logging() -> None:
    """Initialize 1P event logging infrastructure."""
    global _first_party_event_logger_initialized
    if not is_1p_event_logging_enabled():
        return
    _first_party_event_logger_initialized = True


async def shutdown_1p_event_logging() -> None:
    """Flush and shut down the 1P event logger."""
    global _first_party_event_logger_initialized
    _first_party_event_logger_initialized = False


# Legacy alias used by some callers
async def log_first_party_event(event: str, payload: Any = None) -> None:
    log_event_to_1p(event, payload or {})

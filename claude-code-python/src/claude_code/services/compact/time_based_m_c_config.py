"""
Time-based microcompact configuration.
Ported from services/compact/timeBasedMCConfig.ts

Triggers content-clearing microcompact when the gap since the last main-loop
assistant message exceeds a threshold. Running before the API call (in
microcompactMessages) shrinks the prompt sent to the server. Main thread only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict


@dataclass
class TimeBasedMCConfig:
    """Configuration for time-based microcompact.

    Attributes:
        enabled: Master switch.
        gap_threshold_minutes: Trigger when (now - last_assistant_timestamp)
            exceeds this many minutes. 60 is safe — the server 1h cache TTL
            is guaranteed expired, so we never force a miss that would not
            have happened.
        keep_recent: Keep this many most-recent compactable tool results.
    """

    enabled: bool
    gap_threshold_minutes: int
    keep_recent: int


_TIME_BASED_MC_CONFIG_DEFAULTS: Dict[str, Any] = {
    "enabled": False,
    "gap_threshold_minutes": 60,
    "keep_recent": 5,
}


def get_time_based_mc_config() -> TimeBasedMCConfig:
    """Return the current time-based microcompact configuration.

    Reads the ``tengu_slate_heron`` GrowthBook feature flag when available;
    falls back to safe defaults when GrowthBook is unavailable.
    """
    try:
        from claude_code.services.analytics.growthbook import (  # type: ignore
            get_feature_value_cached_may_be_stale,
        )

        raw: Dict[str, Any] = get_feature_value_cached_may_be_stale(
            "tengu_slate_heron",
            _TIME_BASED_MC_CONFIG_DEFAULTS,
        )
    except ImportError:
        raw = _TIME_BASED_MC_CONFIG_DEFAULTS

    return TimeBasedMCConfig(
        enabled=bool(raw.get("enabled", False)),
        gap_threshold_minutes=int(
            raw.get("gapThresholdMinutes", raw.get("gap_threshold_minutes", 60))
        ),
        keep_recent=int(raw.get("keepRecent", raw.get("keep_recent", 5))),
    )

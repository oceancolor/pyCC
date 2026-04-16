"""Cron jitter configuration backed by feature flags.

Ported from cronJitterConfig.ts — separated so the scheduler can be used
without pulling in analytics/GrowthBook dependencies.
"""

from dataclasses import dataclass
from typing import Any, Optional

# Refresh interval: how often to re-fetch the config (ms equivalent kept as
# a Python constant in seconds).
JITTER_CONFIG_REFRESH_S = 60

# Bounds for validation (matching TS constants)
HALF_HOUR_MS = 30 * 60 * 1000
THIRTY_DAYS_MS = 30 * 24 * 60 * 60 * 1000


@dataclass
class CronJitterConfig:
    """Jitter parameters for cron scheduling."""
    recurring_frac: float       # Fraction of interval to use as jitter window
    recurring_cap_ms: int       # Max jitter cap for recurring tasks (ms)
    one_shot_max_ms: int        # Max jitter for one-shot tasks (ms)
    one_shot_floor_ms: int      # Min jitter for one-shot tasks (ms)
    one_shot_minute_mod: int    # Minute modulus for one-shot alignment
    recurring_max_age_ms: int   # Max age before recurring task is considered stale


DEFAULT_CRON_JITTER_CONFIG = CronJitterConfig(
    recurring_frac=0.1,
    recurring_cap_ms=30_000,        # 30 s
    one_shot_max_ms=5 * 60_000,     # 5 min
    one_shot_floor_ms=0,
    one_shot_minute_mod=5,
    recurring_max_age_ms=7 * 24 * 60 * 60 * 1000,  # 7 days
)


def _validate_jitter_config(raw: Any) -> Optional[CronJitterConfig]:
    """Validate raw config dict, returning None if invalid."""
    if not isinstance(raw, dict):
        return None
    try:
        rf = float(raw['recurring_frac'])
        rc = int(raw['recurring_cap_ms'])
        om = int(raw['one_shot_max_ms'])
        of_ = int(raw['one_shot_floor_ms'])
        mm = int(raw['one_shot_minute_mod'])
        ra = int(raw.get('recurring_max_age_ms',
                          DEFAULT_CRON_JITTER_CONFIG.recurring_max_age_ms))
    except (KeyError, ValueError, TypeError):
        return None

    # Bounds checks (mirrors Zod schema)
    if not (0 <= rf <= 1):
        return None
    if not (0 <= rc <= HALF_HOUR_MS):
        return None
    if not (0 <= om <= HALF_HOUR_MS):
        return None
    if not (0 <= of_ <= HALF_HOUR_MS):
        return None
    if not (1 <= mm <= 60):
        return None
    if not (0 <= ra <= THIRTY_DAYS_MS):
        return None
    # Cross-check: floor must not exceed max
    if of_ > om:
        return None

    return CronJitterConfig(
        recurring_frac=rf,
        recurring_cap_ms=rc,
        one_shot_max_ms=om,
        one_shot_floor_ms=of_,
        one_shot_minute_mod=mm,
        recurring_max_age_ms=ra,
    )


def get_cron_jitter_config(
    feature_value_fn: Any = None,
) -> CronJitterConfig:
    """Get cron jitter config from a feature-flag source.

    Args:
        feature_value_fn: Callable() -> Any that returns the raw config dict.
                          If None or raises, falls back to DEFAULT_CRON_JITTER_CONFIG.
    """
    if feature_value_fn is None:
        return DEFAULT_CRON_JITTER_CONFIG
    try:
        raw = feature_value_fn()
    except Exception:
        return DEFAULT_CRON_JITTER_CONFIG
    result = _validate_jitter_config(raw)
    return result if result is not None else DEFAULT_CRON_JITTER_CONFIG

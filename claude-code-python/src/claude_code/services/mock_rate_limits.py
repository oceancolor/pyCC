"""Mock rate limits for ANT-only testing. Ported from services/mockRateLimits.ts

⚠️ WARNING: For internal testing/demo purposes only!
Mock headers may not exactly match the API spec or real-world behavior.
"""
from __future__ import annotations
import os
from typing import Any, Dict, Optional

# -----------------------------------------------------------------------
# Type aliases (matching TS)
# -----------------------------------------------------------------------
MockScenario = str  # see MOCK_SCENARIOS below

MOCK_SCENARIOS = frozenset([
    "normal", "session-limit-reached", "approaching-weekly-limit",
    "weekly-limit-reached", "overage-active", "overage-warning",
    "overage-exhausted", "out-of-credits", "org-zero-credit-limit",
    "org-spend-cap-hit", "member-zero-credit-limit",
    "seat-tier-zero-credit-limit", "opus-limit", "opus-warning",
    "sonnet-limit", "sonnet-warning", "fast-mode-limit",
    "fast-mode-short-limit", "extra-usage-required", "clear",
])

# Module-level mock state
_mock_headers: Dict[str, str] = {}
_is_mock_enabled: bool = False


def _rate_limit_prefix(key: str) -> str:
    return f"anthropic-ratelimit-unified-{key}"


def set_mock_scenario(scenario: MockScenario) -> None:
    """Activate a named mock rate-limit scenario."""
    global _mock_headers, _is_mock_enabled

    if scenario == "clear":
        _mock_headers = {}
        _is_mock_enabled = False
        return

    # Build mock headers per scenario
    now_plus_hour = _iso_now_plus(3600)
    now_plus_day = _iso_now_plus(86400)

    scenario_headers: Dict[str, str] = {
        "normal": {
            _rate_limit_prefix("status"): "allowed",
        },
        "session-limit-reached": {
            _rate_limit_prefix("status"): "rejected",
            _rate_limit_prefix("reset"): now_plus_hour,
            _rate_limit_prefix("representative-claim"): "five_hour",
        },
        "approaching-weekly-limit": {
            _rate_limit_prefix("status"): "allowed_warning",
            _rate_limit_prefix("7d-utilization"): "0.90",
            _rate_limit_prefix("7d-surpassed-threshold"): "1",
            _rate_limit_prefix("reset"): now_plus_day,
        },
        "weekly-limit-reached": {
            _rate_limit_prefix("status"): "rejected",
            _rate_limit_prefix("reset"): now_plus_day,
            _rate_limit_prefix("representative-claim"): "seven_day",
        },
        "overage-active": {
            _rate_limit_prefix("status"): "rejected",
            _rate_limit_prefix("overage-status"): "allowed",
        },
        "overage-warning": {
            _rate_limit_prefix("status"): "allowed",
            _rate_limit_prefix("overage-status"): "allowed_warning",
            _rate_limit_prefix("overage-utilization"): "0.85",
            _rate_limit_prefix("overage-surpassed-threshold"): "1",
        },
        "overage-exhausted": {
            _rate_limit_prefix("status"): "rejected",
            _rate_limit_prefix("overage-status"): "rejected",
            _rate_limit_prefix("overage-reset"): now_plus_day,
        },
        "out-of-credits": {
            _rate_limit_prefix("status"): "rejected",
            _rate_limit_prefix("overage-disabled-reason"): "out_of_credits",
        },
        "opus-limit": {
            _rate_limit_prefix("status"): "rejected",
            _rate_limit_prefix("reset"): now_plus_day,
            _rate_limit_prefix("representative-claim"): "seven_day_opus",
        },
        "sonnet-limit": {
            _rate_limit_prefix("status"): "rejected",
            _rate_limit_prefix("reset"): now_plus_day,
            _rate_limit_prefix("representative-claim"): "seven_day_sonnet",
        },
    }.get(scenario, {})

    _mock_headers = scenario_headers
    _is_mock_enabled = bool(scenario_headers)


def get_mock_rate_limit_headers() -> Optional[Dict[str, str]]:
    """Return the active mock rate-limit headers, or None if disabled."""
    if not _is_mock_enabled:
        return None
    return dict(_mock_headers)


def is_mock_rate_limiting_enabled() -> bool:
    """Return True if mock rate limits are currently active."""
    return _is_mock_enabled


def _iso_now_plus(seconds: int) -> str:
    """Return an ISO-8601 timestamp `seconds` from now."""
    import datetime
    dt = datetime.datetime.utcnow() + datetime.timedelta(seconds=seconds)
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")

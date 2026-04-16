"""
Claude AI rate limit tracking. Ported from services/claudeAiLimits.ts (515 lines → core).
"""
from __future__ import annotations
from typing import Any, Callable, Literal, Optional, Set, TypedDict
import asyncio

RateLimitType = Literal["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet", "overage"]
QuotaStatus = Literal["allowed", "allowed_warning", "rejected"]

RATE_LIMIT_DISPLAY_NAMES: dict = {
    "five_hour": "session limit",
    "seven_day": "weekly limit",
    "seven_day_opus": "Opus limit",
    "seven_day_sonnet": "Sonnet limit",
    "overage": "extra usage",
}


class ClaudeAILimits(TypedDict, total=False):
    status: QuotaStatus
    overage_status: Optional[QuotaStatus]
    rate_limit_type: Optional[RateLimitType]
    resets_at: Optional[str]
    overage_resets_at: Optional[str]
    utilization: Optional[float]
    is_using_overage: bool
    overage_disabled_reason: Optional[str]
    subscription_prompt_tokens_used: Optional[int]
    subscription_token_limit: Optional[int]


_current_limits: ClaudeAILimits = {
    "status": "allowed",
    "overage_status": None,
    "rate_limit_type": None,
    "resets_at": None,
    "overage_resets_at": None,
    "utilization": None,
    "is_using_overage": False,
    "overage_disabled_reason": None,
    "subscription_prompt_tokens_used": None,
    "subscription_token_limit": None,
}

StatusChangeListener = Callable[[ClaudeAILimits], None]
_status_listeners: Set[StatusChangeListener] = set()


def get_current_limits() -> ClaudeAILimits:
    return dict(_current_limits)  # type: ignore


def get_rate_limit_display_name(rate_type: RateLimitType) -> str:
    return RATE_LIMIT_DISPLAY_NAMES.get(rate_type, "usage limit")


def emit_status_change(limits: ClaudeAILimits) -> None:
    global _current_limits
    _current_limits = dict(limits)  # type: ignore
    for listener in list(_status_listeners):
        try:
            listener(limits)
        except Exception:
            pass


currentLimits = _current_limits
statusListeners = _status_listeners


def extract_quota_status_from_headers(headers: dict) -> Optional[ClaudeAILimits]:
    """
    Extract rate limit info from Anthropic response headers.
    Returns updated limits dict or None.
    """
    status_raw = (headers.get("anthropic-ratelimit-unified-status") or "").lower()
    if not status_raw:
        return None

    status_map = {"allowed": "allowed", "allowed_warning": "allowed_warning", "rejected": "rejected"}
    status: QuotaStatus = status_map.get(status_raw, "allowed")  # type: ignore

    resets_at = headers.get("anthropic-ratelimit-unified-reset")
    utilization_raw = headers.get("anthropic-ratelimit-unified-utilized")
    utilization: Optional[float] = None
    if utilization_raw:
        try:
            utilization = float(utilization_raw)
        except ValueError:
            pass

    claim = headers.get("anthropic-ratelimit-unified-representative-claim", "")
    claim_map: dict = {"5h": "five_hour", "7d": "seven_day",
                       "7d-opus": "seven_day_opus", "7d-sonnet": "seven_day_sonnet",
                       "overage": "overage"}
    rate_limit_type: Optional[RateLimitType] = claim_map.get(claim)  # type: ignore

    overage_status_raw = (headers.get("anthropic-ratelimit-unified-overage-status") or "").lower()
    overage_status = status_map.get(overage_status_raw) if overage_status_raw else None

    return {  # type: ignore
        "status": status,
        "overage_status": overage_status,
        "rate_limit_type": rate_limit_type,
        "resets_at": resets_at,
        "overage_resets_at": headers.get("anthropic-ratelimit-unified-overage-reset"),
        "utilization": utilization,
        "is_using_overage": overage_status in ("allowed", "allowed_warning"),
        "overage_disabled_reason": headers.get("anthropic-ratelimit-unified-overage-disabled-reason"),
        "subscription_prompt_tokens_used": None,
        "subscription_token_limit": None,
    }


def extract_quota_status_from_error(error: Exception) -> None:
    """Extract and update limit state from a 429 API error."""
    status_code = getattr(error, "status_code", None) or getattr(error, "status", None)
    if status_code != 429:
        return
    headers = getattr(error, "headers", {}) or {}
    limits = extract_quota_status_from_headers(dict(headers))
    if limits:
        emit_status_change(limits)
    else:
        new_limits = dict(_current_limits)
        new_limits["status"] = "rejected"  # type: ignore
        emit_status_change(new_limits)  # type: ignore


async def check_quota_status() -> None:
    """Poll Claude AI quota status. Stub: no-op without subscriber credentials."""
    pass

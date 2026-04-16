"""Rate limit message generation. Ported from services/rateLimitMessages.ts"""
from __future__ import annotations
from typing import Literal, Optional, TypedDict
from claude_code.services.claude_ai_limits import ClaudeAILimits

RATE_LIMIT_ERROR_PREFIXES = (
    "You've hit your",
    "You've used",
    "You're now using extra usage",
    "You're close to",
    "You're out of extra usage",
)


def is_rate_limit_error_message(text: str) -> bool:
    return any(text.startswith(p) for p in RATE_LIMIT_ERROR_PREFIXES)


class RateLimitMessage(TypedDict):
    message: str
    severity: Literal["error", "warning"]


def get_rate_limit_message(limits: ClaudeAILimits, model: str) -> Optional[RateLimitMessage]:
    """Get the appropriate rate limit message based on limit state."""
    if limits.get("status") == "rejected":
        msg = _get_limit_reached_text(limits, model)
        return {"message": msg, "severity": "error"}
    if limits.get("status") == "allowed_warning":
        util = limits.get("utilization", 0.0)
        if util < 0.7:
            return None
        msg = _get_early_warning_text(limits)
        if msg:
            return {"message": msg, "severity": "warning"}
    return None


def get_rate_limit_error_message(limits: ClaudeAILimits, model: str) -> Optional[str]:
    msg = get_rate_limit_message(limits, model)
    if msg and msg["severity"] == "error":
        return msg["message"]
    return None


def get_rate_limit_warning(limits: ClaudeAILimits, model: str) -> Optional[str]:
    msg = get_rate_limit_message(limits, model)
    if msg and msg["severity"] == "warning":
        return msg["message"]
    return None


def _get_limit_reached_text(limits: ClaudeAILimits, model: str) -> str:
    rate_type = limits.get("rate_limit_type", "")
    resets_at = limits.get("resets_at")
    reset_part = f" · resets soon" if resets_at else ""
    type_map = {
        "seven_day": "weekly limit",
        "five_hour": "session limit",
        "seven_day_opus": "Opus limit",
        "seven_day_sonnet": "Sonnet limit",
    }
    limit_name = type_map.get(rate_type, "usage limit")
    return f"You've hit your {limit_name}{reset_part}"


def _get_early_warning_text(limits: ClaudeAILimits) -> Optional[str]:
    type_map = {
        "seven_day": "weekly limit",
        "five_hour": "session limit",
        "seven_day_opus": "Opus limit",
        "seven_day_sonnet": "Sonnet limit",
        "overage": "extra usage",
    }
    rate_type = limits.get("rate_limit_type")
    limit_name = type_map.get(rate_type or "", "") if rate_type else None
    if not limit_name:
        return None
    used = limits.get("utilization")
    used_str = f" ({int(used * 100)}% used)" if used is not None else ""
    return f"You've used {used_str}of your {limit_name}"

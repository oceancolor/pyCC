"""
Privacy level controls for telemetry and network traffic.
Port of utils/privacyLevel.ts
"""
import os
from typing import Literal

PrivacyLevel = Literal["default", "no-telemetry", "essential-traffic"]


def get_privacy_level() -> PrivacyLevel:
    """Return the most restrictive privacy level from environment variables."""
    if os.environ.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"):
        return "essential-traffic"
    if os.environ.get("DISABLE_TELEMETRY"):
        return "no-telemetry"
    return "default"


def is_essential_traffic_only() -> bool:
    """True when all nonessential network traffic should be suppressed."""
    return get_privacy_level() == "essential-traffic"


def is_telemetry_disabled() -> bool:
    """True when telemetry/analytics should be suppressed."""
    return get_privacy_level() != "default"


def get_essential_traffic_only_reason() -> str | None:
    """Return the env var name responsible for essential-traffic restriction, or None."""
    if os.environ.get("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"):
        return "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"
    return None

"""Claude AI usage/utilization API. Ported from services/api/usage.ts"""
from __future__ import annotations
import os
from typing import Optional, TypedDict


class RateLimit(TypedDict, total=False):
    utilization: Optional[float]
    resets_at: Optional[str]


class ExtraUsage(TypedDict, total=False):
    is_enabled: bool
    monthly_limit: Optional[float]
    used_credits: Optional[float]
    utilization: Optional[float]


class Utilization(TypedDict, total=False):
    five_hour: Optional[RateLimit]
    seven_day: Optional[RateLimit]
    seven_day_opus: Optional[RateLimit]
    seven_day_sonnet: Optional[RateLimit]
    extra_usage: Optional[ExtraUsage]


async def fetch_utilization() -> Optional[Utilization]:
    """Fetch rate limit utilization from Claude API. Stub."""
    return {}

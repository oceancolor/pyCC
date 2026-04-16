"""GrowthBook feature flags stub. Ported from services/analytics/growthbook.ts"""
from __future__ import annotations
from typing import Any, Optional, TypeVar

T = TypeVar("T")

def get_feature_value_cached_may_be_stale(feature_key: str, default_value: T) -> T:
    """Return default (no remote feature flags in this environment)."""
    return default_value

def is_feature_enabled(feature_key: str) -> bool:
    return False

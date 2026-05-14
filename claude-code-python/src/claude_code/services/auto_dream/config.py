"""Auto dream config. Ported from services/autoDream/config.ts"""
from __future__ import annotations
import os


def is_auto_dream_enabled() -> bool:
    """Whether background memory consolidation should run.

    User setting (autoDreamEnabled in settings.json) overrides the GrowthBook
    default when explicitly set; otherwise falls through to feature flag.
    """
    try:
        from claude_code.utils.settings.settings import get_initial_settings
        setting = get_initial_settings().get("autoDreamEnabled")
        if setting is not None:
            return bool(setting)
    except Exception:
        pass

    try:
        from claude_code.services.analytics.growthbook import get_feature_value_cached_may_be_stale
        gb = get_feature_value_cached_may_be_stale("tengu_onyx_plover", None)
        if isinstance(gb, dict):
            return gb.get("enabled") is True
    except Exception:
        pass

    return False

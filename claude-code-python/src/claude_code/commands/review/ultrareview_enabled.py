"""
Ported from: commands/review/ultrareviewEnabled.ts

Runtime feature gate for the /ultrareview command.
"""
from __future__ import annotations

from typing import Any, Optional


# ---------------------------------------------------------------------------
# Stub helper
# ---------------------------------------------------------------------------

def _get_feature_value(feature_key: str, default: Any) -> Any:
    """Read a GrowthBook feature value (cached, may be stale)."""
    try:
        from claude_code.services.analytics.growthbook import (  # type: ignore[import]
            get_feature_value_cached_may_be_stale,
        )
        return get_feature_value_cached_may_be_stale(feature_key, default)
    except ImportError:
        return default


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_ultrareview_enabled() -> bool:
    """
    Return True when the /ultrareview command should be available.

    The GrowthBook ``tengu_review_bughunter_config`` feature flag controls
    visibility.  If the ``enabled`` field in that config is ``True`` the
    command is registered; otherwise it is hidden from ``getCommands()``.
    """
    cfg: Optional[Any] = _get_feature_value("tengu_review_bughunter_config", None)
    if not isinstance(cfg, dict):
        return False
    return cfg.get("enabled") is True

"""Tip display history. Ported from services/tips/tipHistory.ts"""
from __future__ import annotations
import math


def record_tip_shown(tip_id: str) -> None:
    """Record that a tip was shown, keyed to the current startup count."""
    try:
        from claude_code.utils.config import get_global_config, save_global_config
        num_startups = get_global_config().get("numStartups", 0)

        def _update(cfg: dict) -> dict:
            history = dict(cfg.get("tipsHistory") or {})
            if history.get(tip_id) == num_startups:
                return cfg
            return {**cfg, "tipsHistory": {**history, tip_id: num_startups}}

        save_global_config(_update)
    except Exception:
        pass


def get_sessions_since_last_shown(tip_id: str) -> float:
    """Return how many startups have occurred since the tip was last shown.

    Returns math.inf if the tip has never been shown.
    """
    try:
        from claude_code.utils.config import get_global_config
        config = get_global_config()
        last_shown = (config.get("tipsHistory") or {}).get(tip_id)
        if last_shown is None:
            return math.inf
        return int(config.get("numStartups", 0)) - int(last_shown)
    except Exception:
        return math.inf


# Legacy compat
def has_seen_tip(tip_id: str) -> bool:
    return not math.isinf(get_sessions_since_last_shown(tip_id))


def mark_tip_seen(tip_id: str) -> None:
    record_tip_shown(tip_id)

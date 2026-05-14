"""Tip scheduler. Ported from services/tips/tipScheduler.ts"""
from __future__ import annotations
import math
from typing import Any, Optional

from claude_code.services.tips.tip_registry import Tip, get_relevant_tips
from claude_code.services.tips.tip_history import get_sessions_since_last_shown, record_tip_shown


def select_tip_with_longest_time_since_shown(available_tips: list) -> Optional[Tip]:
    """Select the tip that hasn't been shown for the longest time.

    Among available tips, returns the one with the highest session count
    since it was last shown (i.e. the most stale).
    """
    if not available_tips:
        return None
    if len(available_tips) == 1:
        return available_tips[0]

    decorated = [
        (tip, get_sessions_since_last_shown(tip.id))
        for tip in available_tips
    ]
    decorated.sort(key=lambda x: x[1], reverse=True)
    return decorated[0][0]


async def get_tip_to_show_on_spinner(context: Any = None) -> Optional[Tip]:
    """Return the best tip to show on the spinner, or None if tips are disabled."""
    try:
        from claude_code.utils.settings.settings import get_settings_deprecated
        if get_settings_deprecated().get("spinnerTipsEnabled") is False:
            return None
    except Exception:
        pass

    tips = await get_relevant_tips(context)
    return select_tip_with_longest_time_since_shown(tips)


def record_shown_tip(tip: Tip) -> None:
    """Record that a tip was shown and log the analytics event."""
    record_tip_shown(tip.id)

    try:
        from claude_code.services.analytics.index import log_event
        log_event("tengu_tip_shown", {
            "tipIdLength": tip.id,
            "cooldownSessions": tip.cooldown_sessions,
        })
    except Exception:
        pass


# Legacy compat alias
def get_next_tip() -> Optional[Tip]:
    """Synchronous compat shim — returns None (use get_tip_to_show_on_spinner)."""
    return None

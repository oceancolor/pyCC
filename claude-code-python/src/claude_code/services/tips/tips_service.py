"""Tips service. Ported from services/tips (tipRegistry + tipScheduler integration)."""
from __future__ import annotations
from typing import Any, Optional

from claude_code.services.tips.tip_registry import Tip, get_relevant_tips
from claude_code.services.tips.tip_scheduler import (
    get_tip_to_show_on_spinner,
    record_shown_tip,
)
from claude_code.services.tips.tip_history import record_tip_shown


async def get_tip_of_the_day(context: Any = None) -> Optional[str]:
    """Return a tip string to display today, or None if none is due."""
    tip = await get_tip_to_show_on_spinner(context)
    if tip is None:
        return None
    try:
        return await tip.get_content(context)
    except Exception:
        return None


async def mark_tip_seen(tip_id: str) -> None:
    """Record that a tip was seen by the user."""
    record_tip_shown(tip_id)


async def get_and_record_tip(context: Any = None) -> Optional[str]:
    """Get the next tip, record it as shown, and return its content string."""
    tip = await get_tip_to_show_on_spinner(context)
    if tip is None:
        return None
    record_shown_tip(tip)
    try:
        return await tip.get_content(context)
    except Exception:
        return None

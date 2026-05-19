"""Tips service.

Manages the tip-of-the-day system that surfaces contextual usage hints
to the user.  Tips are selected based on session history to avoid showing
the same tip repeatedly.

Ported from: src/services/tips/ (TypeScript)

Exported symbols
----------------
Tip
    Data class describing a single tip.
get_all_tips
    Return the full tip registry.
get_relevant_tips
    Filter tips relevant to the current session context.
record_tip_shown
    Record that a tip was shown in the current session.
get_sessions_since_last_shown
    Return the number of sessions since a given tip was last shown.
get_tip_to_show_on_spinner
    Pick the best tip to show during a long-running operation.
record_shown_tip
    Persist that a tip was shown.
get_tip_of_the_day
    Return today's tip (deterministic for a given date).
mark_tip_seen
    Mark a tip as seen so it won't be shown again soon.
get_and_record_tip
    Return and immediately record the next tip to show.
"""
from __future__ import annotations

from claude_code.services.tips.tip_registry import Tip, get_all_tips, get_relevant_tips
from claude_code.services.tips.tip_history import record_tip_shown, get_sessions_since_last_shown
from claude_code.services.tips.tip_scheduler import get_tip_to_show_on_spinner, record_shown_tip
from claude_code.services.tips.tips_service import (
    get_tip_of_the_day,
    mark_tip_seen,
    get_and_record_tip,
)

__all__ = [
    "Tip",
    "get_all_tips",
    "get_relevant_tips",
    "record_tip_shown",
    "get_sessions_since_last_shown",
    "get_tip_to_show_on_spinner",
    "record_shown_tip",
    "get_tip_of_the_day",
    "mark_tip_seen",
    "get_and_record_tip",
]

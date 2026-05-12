"""
Hint recommendation - recommends plugin hints to users.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class HintRecommendation:
    def __init__(
        self,
        hint_text: str,
        plugin_id: Optional[str] = None,
        command: Optional[str] = None,
    ) -> None:
        self.hint_text = hint_text
        self.plugin_id = plugin_id
        self.command = command


def get_hint_recommendations(
    context: Optional[Dict[str, Any]] = None,
    installed_plugins: Optional[List[str]] = None,
) -> List[HintRecommendation]:
    """Get contextual hint recommendations for the user."""
    hints: List[HintRecommendation] = []
    # Stub implementation: no hints in Python port
    return hints


def should_show_hint(
    hint_key: str,
    last_shown_at: Optional[int] = None,
    min_interval_ms: int = 24 * 60 * 60 * 1000,
) -> bool:
    """Check if a hint should be shown based on last shown time."""
    if last_shown_at is None:
        return True
    import time
    elapsed = int(time.time() * 1000) - last_shown_at
    return elapsed >= min_interval_ms

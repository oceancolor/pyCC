"""
Denial tracking - tracks consecutive denials for auto-mode permission classifiers.
"""

from __future__ import annotations

from typing import Dict


class DenialTrackingState:
    def __init__(self) -> None:
        self.consecutive_denials: int = 0
        self.total_denials: int = 0


DENIAL_LIMITS = {
    "max_consecutive": 3,
    "max_total": 10,
}


def create_initial_denial_tracking_state() -> DenialTrackingState:
    """Create an initial denial tracking state."""
    return DenialTrackingState()


def record_denial(state: DenialTrackingState) -> DenialTrackingState:
    """Record a denial and return updated state."""
    new_state = DenialTrackingState()
    new_state.consecutive_denials = state.consecutive_denials + 1
    new_state.total_denials = state.total_denials + 1
    return new_state


def record_allow(state: DenialTrackingState) -> DenialTrackingState:
    """Record an allow and reset consecutive denials."""
    new_state = DenialTrackingState()
    new_state.consecutive_denials = 0
    new_state.total_denials = state.total_denials
    return new_state


def should_fallback_to_prompting(state: DenialTrackingState) -> bool:
    """Check if we should fall back to prompting the user."""
    return (
        state.consecutive_denials >= DENIAL_LIMITS["max_consecutive"]
        or state.total_denials >= DENIAL_LIMITS["max_total"]
    )

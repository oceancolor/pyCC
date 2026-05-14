"""Claude AI limits hook. Ported from services/claudeAiLimitsHook.ts (React hook → Python observable)"""
from __future__ import annotations
from typing import Callable, Set

# Module-level listener registry (mirrors TS statusListeners Set)
_status_listeners: Set[Callable] = set()


def subscribe_to_claude_ai_limits(listener: Callable) -> Callable:
    """Subscribe to Claude AI limits updates.

    Args:
        listener: Callable that receives a dict of current limits.

    Returns:
        Unsubscribe function — call it to remove the listener.
    """
    _status_listeners.add(listener)

    def unsubscribe() -> None:
        _status_listeners.discard(listener)

    return unsubscribe


def get_claude_ai_limits() -> dict:
    """Return the current Claude AI limits (synchronous snapshot)."""
    try:
        from claude_code.services.claude_ai_limits import current_limits
        return dict(current_limits)
    except Exception:
        return {}


def notify_limits_change(new_limits: dict) -> None:
    """Notify all registered listeners of a limits change."""
    for listener in list(_status_listeners):
        try:
            listener(new_limits)
        except Exception:
            pass


# Alias matching the TS hook name pattern
use_claude_ai_limits = get_claude_ai_limits

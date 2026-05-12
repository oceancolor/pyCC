"""
Compact warning state.
Ported from services/compact/compactWarningState.ts
"""
from __future__ import annotations

from typing import Callable, List

# Simple observable bool state
_value: bool = False
_listeners: List[Callable[[bool], None]] = []


def get_compact_warning_state() -> bool:
    return _value


def suppress_compact_warning() -> None:
    """Suppress the compact warning. Call after successful compaction."""
    global _value
    _value = True
    for listener in _listeners:
        try:
            listener(_value)
        except Exception:
            pass


def clear_compact_warning_suppression() -> None:
    """Clear the compact warning suppression. Called at start of new compact attempt."""
    global _value
    _value = False
    for listener in _listeners:
        try:
            listener(_value)
        except Exception:
            pass


def subscribe_compact_warning_state(listener: Callable[[bool], None]) -> Callable[[], None]:
    _listeners.append(listener)
    def unsubscribe() -> None:
        try:
            _listeners.remove(listener)
        except ValueError:
            pass
    return unsubscribe

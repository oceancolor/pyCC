"""
Tiny listener-set primitive for pure event signals (no stored state).
Ported from utils/signal.ts

Distinct from a store — there is no snapshot, no getState. Use this when
subscribers only need to know "something happened", optionally with event
args, not "what is the current value".
"""
from __future__ import annotations

from typing import Any, Callable, Generic, List, Optional, Tuple, TypeVar

_Args = TypeVar("_Args")


class Signal(Generic[_Args]):
    """Minimal observable signal with subscribe/emit/clear.

    Usage::

        from_setting_changed: Signal = create_signal()
        from_setting_changed.subscribe(lambda source: print("changed:", source))
        from_setting_changed.emit("userSettings")
    """

    __slots__ = ("_listeners",)

    def __init__(self) -> None:
        self._listeners: List[Callable[..., Any]] = []

    def subscribe(self, listener: Callable[..., Any]) -> Callable[[], None]:
        """Subscribe a listener. Returns an unsubscribe function."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            try:
                self._listeners.remove(listener)
            except ValueError:
                pass

        return unsubscribe

    def emit(self, *args: Any) -> None:
        """Call all subscribed listeners with the given arguments."""
        for listener in list(self._listeners):
            try:
                listener(*args)
            except Exception:
                pass

    def clear(self) -> None:
        """Remove all listeners. Useful in dispose/reset paths."""
        self._listeners.clear()


def create_signal() -> Signal:
    """Create a new Signal instance."""
    return Signal()

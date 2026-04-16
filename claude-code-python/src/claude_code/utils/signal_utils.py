"""
Signal primitive — lightweight pub/sub with no stored state.
Ported from signal.ts
"""
from __future__ import annotations
from typing import Callable, Generic, List, Set, TypeVar

Args = TypeVar("Args")


class Signal(Generic[Args]):
    """Listener-set primitive for pure event signals."""

    def __init__(self) -> None:
        self._listeners: Set[Callable] = set()

    def subscribe(self, listener: Callable) -> Callable[[], None]:
        self._listeners.add(listener)
        def unsubscribe() -> None:
            self._listeners.discard(listener)
        return unsubscribe

    def emit(self, *args) -> None:
        for listener in list(self._listeners):
            listener(*args)

    def clear(self) -> None:
        self._listeners.clear()


def create_signal() -> Signal:
    return Signal()

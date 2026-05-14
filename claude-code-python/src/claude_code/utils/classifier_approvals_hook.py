"""Classifier approvals hook. Ported from classifierApprovalsHook.ts.

The TypeScript source uses React's useSyncExternalStore to subscribe to the
classifierApprovals store.  In Python we provide a plain observable wrapper
so non-React code can subscribe to the same state changes.
"""
from __future__ import annotations

import threading
from typing import Callable, Dict, Set

__all__ = [
    "use_is_classifier_checking",
    "is_classifier_checking",
    "set_classifier_checking",
    "subscribe_classifier_checking",
    "ClassifierCheckingObserver",
]

# Internal state: set of tool_use_ids currently being classifier-checked
_checking_ids: Set[str] = set()
_listeners: list[Callable[[], None]] = []
_lock = threading.Lock()


def is_classifier_checking(tool_use_id: str) -> bool:
    """Return whether the classifier is currently checking *tool_use_id*."""
    with _lock:
        return tool_use_id in _checking_ids


def set_classifier_checking(tool_use_id: str, checking: bool) -> None:
    """Mark or unmark *tool_use_id* as being classifier-checked."""
    with _lock:
        if checking:
            _checking_ids.add(tool_use_id)
        else:
            _checking_ids.discard(tool_use_id)
    _notify_listeners()


def subscribe_classifier_checking(listener: Callable[[], None]) -> Callable[[], None]:
    """Register *listener* for state changes. Returns an unsubscribe callable."""
    with _lock:
        _listeners.append(listener)

    def unsubscribe() -> None:
        with _lock:
            try:
                _listeners.remove(listener)
            except ValueError:
                pass

    return unsubscribe


def _notify_listeners() -> None:
    with _lock:
        snapshot = list(_listeners)
    for fn in snapshot:
        try:
            fn()
        except Exception:
            pass


def use_is_classifier_checking(tool_use_id: str) -> bool:
    """Return whether the classifier is currently checking *tool_use_id*.

    Directly reads the store.  In an async / event-loop context callers should
    subscribe via ClassifierCheckingObserver instead to receive live updates.
    """
    return is_classifier_checking(tool_use_id)


class ClassifierCheckingObserver:
    """Subscribe to classifier-checking state changes for a given tool_use_id.

    Usage::

        obs = ClassifierCheckingObserver("tool-123", callback=my_fn)
        obs.start()
        ...
        obs.stop()
    """

    def __init__(
        self,
        tool_use_id: str,
        callback: Callable[[bool], None],
    ) -> None:
        self._tool_use_id = tool_use_id
        self._callback = callback
        self._unsubscribe: Callable[[], None] | None = None
        self._obs_lock = threading.Lock()

    def start(self) -> None:
        """Begin listening for state changes."""
        with self._obs_lock:
            if self._unsubscribe is not None:
                return

            def _on_change() -> None:
                self._callback(is_classifier_checking(self._tool_use_id))

            self._unsubscribe = subscribe_classifier_checking(_on_change)

    def stop(self) -> None:
        """Stop listening for state changes."""
        with self._obs_lock:
            if self._unsubscribe is not None:
                self._unsubscribe()
                self._unsubscribe = None

    @property
    def current(self) -> bool:
        """Snapshot of the current checking state."""
        return is_classifier_checking(self._tool_use_id)

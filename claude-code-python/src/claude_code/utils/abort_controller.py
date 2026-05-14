"""AbortController abstraction. Ported from abortController.ts.

Wraps asyncio.Event to provide an API similar to the DOM AbortController /
AbortSignal used throughout the TypeScript codebase.  The key difference is
that Python's asyncio.Event is edge-triggered, so once aborted the signal
stays set.
"""
from __future__ import annotations

import asyncio
from typing import Callable, List, Optional

__all__ = [
    "AbortController",
    "AbortSignal",
    "create_abort_controller",
    "combine_signals",
]


class AbortSignal:
    """Read-only view of an abort state, analogous to DOM AbortSignal."""

    def __init__(self, event: asyncio.Event) -> None:
        self._event = event
        self._listeners: List[Callable[[], None]] = []

    @property
    def aborted(self) -> bool:
        """True once the controller has been aborted."""
        return self._event.is_set()

    async def wait(self) -> None:
        """Suspend until the signal is aborted."""
        await self._event.wait()

    def add_listener(self, callback: Callable[[], None]) -> None:
        """Register *callback* to be called when the signal is aborted."""
        if self._event.is_set():
            callback()
        else:
            self._listeners.append(callback)

    def _fire(self) -> None:
        for fn in self._listeners:
            try:
                fn()
            except Exception:
                pass
        self._listeners.clear()


class AbortController:
    """Abort controller mirroring the DOM AbortController API.

    Usage::

        ctrl = AbortController()
        signal = ctrl.signal

        async def do_work():
            try:
                await asyncio.wait_for(some_task(), timeout=10)
            except asyncio.CancelledError:
                pass

        ctrl.abort()  # cancel ongoing operations
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._signal = AbortSignal(self._event)

    def abort(self, reason: Optional[str] = None) -> None:
        """Abort – idempotent."""
        if not self._event.is_set():
            self._event.set()
            self._signal._fire()

    @property
    def signal(self) -> AbortSignal:
        """The associated AbortSignal (read-only view)."""
        return self._signal

    @property
    def is_aborted(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        """Suspend until abort() is called."""
        await self._event.wait()


def create_abort_controller() -> AbortController:
    """Factory helper: return a new AbortController."""
    return AbortController()


def combine_signals(*controllers: AbortController) -> AbortController:
    """Return a new controller that aborts when ANY of *controllers* aborts."""
    combined = AbortController()

    def _check() -> None:
        if any(c.is_aborted for c in controllers):
            combined.abort()

    for c in controllers:
        c.signal.add_listener(_check)

    return combined

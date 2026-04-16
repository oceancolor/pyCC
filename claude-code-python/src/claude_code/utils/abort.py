# 原始 TS: utils/abortController.ts
"""
Abort controller utilities - cancellation signals for async operations.
Python equivalent using asyncio.Event and threading.Event.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Optional


class AbortController:
    """
    Python equivalent of the Web AbortController API.
    Uses asyncio.Event for async contexts and threading.Event for sync contexts.
    """

    def __init__(self) -> None:
        self._event = asyncio.Event()
        self._thread_event = threading.Event()
        self._reason: Optional[str] = None

    @property
    def signal(self) -> "AbortSignal":
        return AbortSignal(self)

    def abort(self, reason: Optional[str] = None) -> None:
        """Abort the operation with an optional reason."""
        self._reason = reason
        self._event.set()
        self._thread_event.set()

    @property
    def aborted(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> Optional[str]:
        return self._reason


class AbortSignal:
    """
    Read-only view of an AbortController's state.
    Equivalent to AbortSignal in the Web API / Node.js.
    """

    def __init__(self, controller: AbortController) -> None:
        self._controller = controller

    @property
    def aborted(self) -> bool:
        return self._controller.aborted

    @property
    def reason(self) -> Optional[str]:
        return self._controller.reason

    async def wait(self) -> None:
        """Wait until the signal is aborted."""
        await self._controller._event.wait()

    def check(self) -> None:
        """Raise AbortError if signal is aborted (convenience method)."""
        from claude_code.utils.errors import AbortError
        if self.aborted:
            raise AbortError(self.reason or "Operation aborted")


def create_abort_controller(max_listeners: int = 50) -> AbortController:
    """
    Creates an AbortController.
    原始 TS: createAbortController()
    
    Note: max_listeners parameter kept for API compatibility but not used in Python.
    """
    return AbortController()


def create_child_abort_controller(
    parent: AbortController,
    max_listeners: int = 50,
) -> AbortController:
    """
    Creates a child AbortController that aborts when its parent aborts.
    原始 TS: createChildAbortController()
    
    Aborting the child does NOT affect the parent.
    """
    child = create_abort_controller(max_listeners)

    # Fast path: parent already aborted
    if parent.aborted:
        child.abort(parent.reason)
        return child

    # Set up propagation using asyncio task
    async def _propagate() -> None:
        await parent._event.wait()
        if not child.aborted:
            child.abort(parent.reason)

    # Schedule propagation (will run when event loop is available)
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_propagate())
    except RuntimeError:
        pass  # No event loop available

    return child


def combine_abort_signals(*controllers: AbortController) -> AbortController:
    """
    Creates a combined AbortController that aborts if ANY of the given
    controllers abort.
    """
    combined = create_abort_controller()

    for ctrl in controllers:
        if ctrl.aborted:
            combined.abort(ctrl.reason)
            return combined

    async def _watch(c: AbortController) -> None:
        await c._event.wait()
        if not combined.aborted:
            combined.abort(c.reason)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            for ctrl in controllers:
                asyncio.ensure_future(_watch(ctrl))
    except RuntimeError:
        pass

    return combined

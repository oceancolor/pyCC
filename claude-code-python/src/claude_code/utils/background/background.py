"""Background task utilities. Ported from utils/background/."""

from __future__ import annotations

import asyncio
import logging
import weakref
from typing import Any, Callable, Coroutine, List, Optional, TypeVar

_T = TypeVar("_T")
log = logging.getLogger(__name__)

# Keep a strong reference to running tasks so they are not GC'd.
_active_tasks: weakref.WeakSet = weakref.WeakSet()


def schedule_background(
    coro: Coroutine[Any, Any, _T],
    name: Optional[str] = None,
    on_error: Optional[Callable[[Exception], None]] = None,
) -> "asyncio.Task[_T]":
    """Schedule a coroutine as a fire-and-forget background task.

    The task is tracked in a weak set so it can be garbage-collected once
    complete, without leaking memory.

    Args:
        coro: The coroutine to run in the background.
        name: Optional task name for debugging.
        on_error: Optional callback invoked with the exception on failure.

    Returns:
        The created :class:`asyncio.Task`.
    """
    loop = asyncio.get_event_loop()
    task: asyncio.Task = loop.create_task(coro, name=name)
    _active_tasks.add(task)

    def _done_callback(t: asyncio.Task) -> None:
        exc = t.exception() if not t.cancelled() else None
        if exc is not None:
            if on_error:
                try:
                    on_error(exc)
                except Exception:
                    pass
            else:
                log.debug("Background task %r raised: %s", name or "?", exc)

    task.add_done_callback(_done_callback)
    return task


def run_background_tasks_sync(
    coros: List[Coroutine[Any, Any, Any]],
    timeout: Optional[float] = None,
) -> None:
    """Run a list of coroutines synchronously, discarding results.

    Intended for use in startup/shutdown sequences where an event loop may
    not already be running.

    Args:
        coros: List of coroutines to execute concurrently.
        timeout: Optional timeout in seconds for the whole group.
    """
    async def _run_all() -> None:
        await asyncio.gather(*coros, return_exceptions=True)

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(_run_all())
        else:
            if timeout is not None:
                loop.run_until_complete(asyncio.wait_for(_run_all(), timeout=timeout))
            else:
                loop.run_until_complete(_run_all())
    except Exception as exc:
        log.debug("run_background_tasks_sync error: %s", exc)


async def drain_background_tasks() -> None:
    """Await all currently tracked background tasks.

    Useful in tests or during graceful shutdown to ensure background work
    completes before the process exits.
    """
    tasks = list(_active_tasks)
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

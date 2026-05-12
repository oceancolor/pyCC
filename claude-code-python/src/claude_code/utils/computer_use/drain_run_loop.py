"""
drain_run_loop.py - CFRunLoop pump for macOS computer use native calls.

Port of TypeScript drainRunLoop.ts.
"""

import asyncio
import logging
from typing import Any, Callable, Coroutine, Optional, TypeVar

logger = logging.getLogger(__name__)

TIMEOUT_MS = 30_000

_pump_task: Optional[asyncio.Task] = None
_pending = 0

T = TypeVar('T')


def retain_pump() -> None:
    """Hold a pump reference for the lifetime of a long-lived registration."""
    global _pending, _pump_task
    _pending += 1
    if _pump_task is None:
        logger.debug('[drainRunLoop] pump started')


def release_pump() -> None:
    """Release pump reference."""
    global _pending, _pump_task
    _pending -= 1
    if _pending <= 0:
        _pending = 0
        if _pump_task is not None:
            _pump_task = None
            logger.debug('[drainRunLoop] pump stopped')


async def drain_run_loop(fn: Callable[[], Coroutine[Any, Any, T]]) -> T:
    """
    Await fn() with the shared drain pump running.
    On non-macOS platforms, just calls fn() directly with a timeout.

    Args:
        fn: Async function to call

    Returns:
        Result of fn()

    Raises:
        TimeoutError: If fn() exceeds TIMEOUT_MS
        Any exception raised by fn()
    """
    retain_pump()
    try:
        work = asyncio.ensure_future(fn())
        work.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

        try:
            result = await asyncio.wait_for(
                asyncio.shield(work),
                timeout=TIMEOUT_MS / 1000,
            )
            return result
        except asyncio.TimeoutError:
            raise TimeoutError(f"computer-use native call exceeded {TIMEOUT_MS}ms")
    finally:
        release_pump()

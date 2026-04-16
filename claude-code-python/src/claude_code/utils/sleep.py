"""
sleep.py - Abort-responsive async sleep utilities.

Ported from sleep.ts.

Provides:
  sleep(ms, signal, *, throw_on_abort, abort_error_factory, unref)
    Async sleep that resolves after `ms` milliseconds, or when `signal` is
    cancelled.  If throw_on_abort=True (or abort_error_factory is given),
    the coroutine raises instead of returning silently.

  with_timeout(coro_or_future, ms, message)
    Race an awaitable against a timeout; raises TimeoutError(message) if
    it doesn't settle in time.

Python notes:
  - asyncio.Event replaces the AbortSignal listener pattern.
  - `unref` has no direct Python equivalent (asyncio tasks don't block
    process exit the same way), so the parameter is accepted but ignored.
"""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Optional, TypeVar

T = TypeVar("T")


async def sleep(
    ms: float,
    signal: Optional[asyncio.Event] = None,
    *,
    throw_on_abort: bool = False,
    abort_error_factory: Optional[Callable[[], Exception]] = None,
    unref: bool = False,  # accepted for API compatibility; no-op in Python
) -> None:
    """
    Sleep for *ms* milliseconds.

    If *signal* (an ``asyncio.Event``) is set before or during the sleep:
    - By default, returns silently (caller should check ``signal.is_set()``).
    - If *throw_on_abort* is True or *abort_error_factory* is given, raises
      the error returned by *abort_error_factory()* (default: ``Exception('aborted')``).

    Args:
        ms:                   Duration in milliseconds.
        signal:               Optional cancellation token (asyncio.Event).
        throw_on_abort:       Raise on abort instead of resolving silently.
        abort_error_factory:  Factory for the raised exception (implies throw_on_abort).
        unref:                Ignored (no-op in asyncio).
    """
    should_throw = throw_on_abort or abort_error_factory is not None

    # Check abort before setting up the timer (mirrors TS pre-check)
    if signal is not None and signal.is_set():
        if should_throw:
            raise (abort_error_factory() if abort_error_factory else Exception("aborted"))
        return

    delay_sec = ms / 1000.0

    if signal is None:
        await asyncio.sleep(delay_sec)
        return

    # Race sleep against abort signal
    sleep_task = asyncio.ensure_future(asyncio.sleep(delay_sec))
    abort_task = asyncio.ensure_future(signal.wait())
    done, pending = await asyncio.wait(
        [sleep_task, abort_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()
        try:
            await t
        except asyncio.CancelledError:
            pass

    if abort_task in done:
        if should_throw:
            raise (abort_error_factory() if abort_error_factory else Exception("aborted"))


async def with_timeout(
    awaitable: Awaitable[T],
    ms: float,
    message: str,
) -> T:
    """
    Race *awaitable* against a timeout of *ms* milliseconds.

    Raises ``asyncio.TimeoutError`` (with *message*) if the awaitable does
    not settle in time.  The underlying task is cancelled on timeout.
    """
    try:
        return await asyncio.wait_for(awaitable, timeout=ms / 1000.0)
    except asyncio.TimeoutError:
        raise asyncio.TimeoutError(message)

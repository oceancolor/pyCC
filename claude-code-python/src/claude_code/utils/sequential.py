"""Sequential execution wrapper. Ported from sequential.ts.

Creates a sequential execution wrapper for async functions to prevent race
conditions.  Ensures that concurrent calls to the wrapped function are
executed one at a time in the order they were received, while preserving
the correct return values.

This is useful for operations that must be performed sequentially, such as
file writes or database updates that could cause conflicts if executed
concurrently.
"""
from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable, Coroutine, TypeVar

__all__ = [
    "sequential",
    "sequential_with_queue",
]

T = TypeVar("T")


def sequential(fn: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    """Wrap an async function so concurrent calls are serialised via a lock.

    The simplest form — suitable when callers can tolerate slight ordering
    variance (the lock is FIFO only if the event loop schedules them that way).

    Usage::

        @sequential
        async def write_file(path: str, content: str) -> None:
            ...

        # Or wrap an existing function:
        safe_write = sequential(write_file)
    """
    lock = asyncio.Lock()

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        async with lock:
            return await fn(*args, **kwargs)

    return wrapper  # type: ignore[return-value]


def sequential_with_queue(
    fn: Callable[..., Coroutine[Any, Any, T]],
) -> Callable[..., Coroutine[Any, Any, T]]:
    """Wrap an async function with a strict FIFO execution queue.

    Unlike the lock-based version, this guarantees true FIFO ordering:
    calls are enqueued and processed in the exact order they arrive,
    even if the event loop would otherwise reorder lock-waiting tasks.

    Port of the TypeScript sequential() implementation which uses an
    explicit queue with resolve/reject callbacks.
    """
    queue: list[tuple[tuple, dict, asyncio.Future]] = []
    processing = False

    async def process_queue() -> None:
        nonlocal processing
        if processing:
            return
        processing = True
        try:
            while queue:
                args, kwargs, future = queue.pop(0)
                try:
                    result = await fn(*args, **kwargs)
                    if not future.done():
                        future.set_result(result)
                except Exception as exc:
                    if not future.done():
                        future.set_exception(exc)
        finally:
            processing = False
            if queue:
                asyncio.ensure_future(process_queue())

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> T:
        loop = asyncio.get_event_loop()
        future: asyncio.Future[T] = loop.create_future()
        queue.append((args, kwargs, future))
        asyncio.ensure_future(process_queue())
        return await future

    return wrapper  # type: ignore[return-value]

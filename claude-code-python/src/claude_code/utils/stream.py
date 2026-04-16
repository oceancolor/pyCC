"""Async stream utility — push-based async iterator.

Ported from stream.ts (Stream<T> class portion).
"""

import asyncio
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar('T')


class Stream(Generic[T]):
    """Push-based async iterable/iterator.

    Producer calls ``enqueue(value)`` to push items, ``done()`` to signal
    completion, and ``error(exc)`` to signal failure.  Consumer iterates
    with ``async for item in stream:``.

    The stream can only be iterated once; a second ``async for`` raises
    RuntimeError.
    """

    def __init__(self, returned: Optional[Callable[[], None]] = None) -> None:
        self._queue: list[T] = []
        self._waiters: list[asyncio.Future[T]] = []
        self._done = False
        self._error: Optional[BaseException] = None
        self._started = False
        self._returned = returned

    # ------------------------------------------------------------------
    # Async iteration protocol
    # ------------------------------------------------------------------

    def __aiter__(self) -> 'Stream[T]':
        if self._started:
            raise RuntimeError('Stream can only be iterated once')
        self._started = True
        return self

    async def __anext__(self) -> T:
        if self._queue:
            return self._queue.pop(0)
        if self._done:
            raise StopAsyncIteration
        if self._error is not None:
            raise self._error

        loop = asyncio.get_event_loop()
        fut: asyncio.Future[T] = loop.create_future()
        self._waiters.append(fut)
        try:
            return await fut
        except StopAsyncIteration:
            raise
        except asyncio.CancelledError:
            raise

    # ------------------------------------------------------------------
    # Producer API
    # ------------------------------------------------------------------

    def enqueue(self, value: T) -> None:
        """Push a value; wakes a waiting consumer if any."""
        if self._waiters:
            fut = self._waiters.pop(0)
            if not fut.done():
                fut.set_result(value)
        else:
            self._queue.append(value)

    def done(self) -> None:
        """Signal that no more values will be produced."""
        self._done = True
        for fut in self._waiters:
            if not fut.done():
                fut.set_exception(StopAsyncIteration())
        self._waiters.clear()

    def error(self, exc: BaseException) -> None:
        """Signal an error; wakes waiting consumers with the exception."""
        self._error = exc
        for fut in self._waiters:
            if not fut.done():
                fut.set_exception(exc)
        self._waiters.clear()

    def close(self) -> None:
        """Alias for done(); also calls the optional returned callback."""
        self._done = True
        if self._returned:
            self._returned()
        for fut in self._waiters:
            if not fut.done():
                fut.set_exception(StopAsyncIteration())
        self._waiters.clear()

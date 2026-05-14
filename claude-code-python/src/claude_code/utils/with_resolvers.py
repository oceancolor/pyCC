"""Promise.withResolvers equivalent for Python. Ported from withResolvers.ts.

Polyfill for Promise.withResolvers() (ES2024, Node 22+).  The TypeScript
source documents that Node >=18 is supported but Promise.withResolvers is
only available from Node 22, hence the manual implementation.

In Python we model this using asyncio.Future (for async contexts) and
threading.Event-based equivalents for synchronous contexts.
"""
from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, Generic, Optional, Tuple, TypeVar

__all__ = [
    "FutureWithResolvers",
    "SyncFutureWithResolvers",
    "with_resolvers",
    "with_resolvers_sync",
]

T = TypeVar("T")


class FutureWithResolvers(Generic[T]):
    """Asyncio-based deferred with explicit resolve/reject handles.

    Mirrors the ES2024 PromiseWithResolvers<T> object::

        { promise, resolve, reject }

    Usage::

        wr = FutureWithResolvers()
        asyncio.get_event_loop().call_later(0.1, wr.resolve, 42)
        result = await wr.promise   # → 42
    """

    def __init__(self, loop: Optional[asyncio.AbstractEventLoop] = None) -> None:
        self._loop = loop or asyncio.get_event_loop()
        self._future: asyncio.Future[T] = self._loop.create_future()

    @property
    def promise(self) -> asyncio.Future[T]:
        """The underlying future – await this to receive the value."""
        return self._future

    def resolve(self, value: T) -> None:
        """Resolve the future with *value* (no-op if already settled)."""
        if not self._future.done():
            self._future.set_result(value)

    def reject(self, reason: BaseException) -> None:
        """Reject the future with *reason* (no-op if already settled)."""
        if not self._future.done():
            self._future.set_exception(reason)

    @property
    def is_settled(self) -> bool:
        """Return True if the future has been resolved or rejected."""
        return self._future.done()


class SyncFutureWithResolvers(Generic[T]):
    """Thread-safe deferred using threading primitives (non-async contexts)."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._result: Optional[T] = None
        self._exception: Optional[BaseException] = None

    def resolve(self, value: T) -> None:
        """Resolve with *value*."""
        if not self._event.is_set():
            self._result = value
            self._event.set()

    def reject(self, reason: BaseException) -> None:
        """Reject with *reason*."""
        if not self._event.is_set():
            self._exception = reason
            self._event.set()

    def result(self, timeout: Optional[float] = None) -> T:
        """Block until resolved/rejected and return the value or raise."""
        self._event.wait(timeout=timeout)
        if self._exception is not None:
            raise self._exception
        return self._result  # type: ignore[return-value]

    @property
    def is_settled(self) -> bool:
        return self._event.is_set()


def with_resolvers(loop: Optional[asyncio.AbstractEventLoop] = None) -> FutureWithResolvers:
    """Create and return a FutureWithResolvers (async context)."""
    return FutureWithResolvers(loop=loop)


def with_resolvers_sync() -> SyncFutureWithResolvers:
    """Create and return a SyncFutureWithResolvers (sync/threaded context)."""
    return SyncFutureWithResolvers()

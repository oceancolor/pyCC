"""Promise.withResolvers equivalent for Python. Ported from withResolvers.ts"""
from __future__ import annotations
import asyncio
from typing import Generic, Optional, Tuple, TypeVar

T = TypeVar("T")

class FutureWithResolvers(Generic[T]):
    def __init__(self) -> None:
        self._future: asyncio.Future = asyncio.get_event_loop().create_future()

    @property
    def promise(self) -> asyncio.Future:
        return self._future

    def resolve(self, value: T) -> None:
        if not self._future.done():
            self._future.set_result(value)

    def reject(self, reason: Exception) -> None:
        if not self._future.done():
            self._future.set_exception(reason)

def with_resolvers() -> FutureWithResolvers:
    return FutureWithResolvers()

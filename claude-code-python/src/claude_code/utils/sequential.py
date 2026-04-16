"""
Sequential execution wrapper — ensures async calls run one at a time.
Ported from sequential.ts
"""
from __future__ import annotations
import asyncio
from typing import Any, Callable, Coroutine, TypeVar

T = TypeVar("T")


def sequential(fn: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
    """Wrap an async function so concurrent calls queue and run sequentially."""
    lock = asyncio.Lock()

    async def wrapper(*args: Any, **kwargs: Any) -> T:
        async with lock:
            return await fn(*args, **kwargs)

    return wrapper

# 原始 TS: utils/interruptible.ts
"""可中断异步操作包装"""
from __future__ import annotations
import asyncio
from typing import Any, Callable, Coroutine, Optional, TypeVar

T = TypeVar("T")


async def with_timeout(coro: Coroutine[Any, Any, T], seconds: float) -> Optional[T]:
    """带超时的协程执行，超时返回 None"""
    try:
        return await asyncio.wait_for(coro, timeout=seconds)
    except asyncio.TimeoutError:
        return None


async def interruptible(
    coro: Coroutine[Any, Any, T],
    abort_event: Optional[asyncio.Event] = None,
) -> Optional[T]:
    """可被 abort_event 中断的协程执行"""
    if abort_event is None:
        return await coro

    task = asyncio.create_task(coro)
    abort_task = asyncio.create_task(abort_event.wait())

    done, pending = await asyncio.wait(
        {task, abort_task}, return_when=asyncio.FIRST_COMPLETED
    )
    for t in pending:
        t.cancel()

    if task in done and not task.cancelled():
        return task.result()
    return None


async def race(*coros: Coroutine) -> Any:
    """返回最先完成的协程的结果"""
    tasks = [asyncio.create_task(c) for c in coros]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()
    return next(iter(done)).result()

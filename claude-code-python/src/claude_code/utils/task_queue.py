# 原始 TS: utils/taskQueue.ts
"""任务队列（顺序执行异步任务）"""
from __future__ import annotations
import asyncio
from typing import Any, Callable, Coroutine, List, Optional


class TaskQueue:
    """顺序执行的异步任务队列"""

    def __init__(self) -> None:
        self._queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._worker_task: Optional[asyncio.Task] = None

    async def _worker(self) -> None:
        while self._running:
            try:
                fn = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                try:
                    await fn()
                except Exception:
                    pass
                finally:
                    self._queue.task_done()
            except asyncio.TimeoutError:
                continue

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._worker_task = asyncio.get_event_loop().create_task(self._worker())

    def stop(self) -> None:
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()

    def enqueue(self, fn: Callable[[], Coroutine[Any, Any, Any]]) -> None:
        self._queue.put_nowait(fn)

    async def join(self) -> None:
        await self._queue.join()

    @property
    def size(self) -> int:
        return self._queue.qsize()

# 原始 TS: utils/cron.ts / utils/cronScheduler.ts
"""内部 cron 任务调度（后台周期任务）"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional


@dataclass
class CronTask:
    name: str
    interval_seconds: float
    fn: Callable[[], Coroutine[Any, Any, None]]
    last_run: float = 0.0
    enabled: bool = True

    def is_due(self) -> bool:
        return self.enabled and (time.monotonic() - self.last_run) >= self.interval_seconds

    async def run(self) -> None:
        self.last_run = time.monotonic()
        await self.fn()


class CronScheduler:
    """简单的异步 cron 调度器"""

    def __init__(self, tick_interval: float = 5.0) -> None:
        self._tasks: Dict[str, CronTask] = {}
        self._tick_interval = tick_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    def register(self, name: str, interval_seconds: float,
                 fn: Callable[[], Coroutine[Any, Any, None]]) -> None:
        self._tasks[name] = CronTask(name=name, interval_seconds=interval_seconds, fn=fn)

    def unregister(self, name: str) -> None:
        self._tasks.pop(name, None)

    async def _loop(self) -> None:
        while self._running:
            for task in list(self._tasks.values()):
                if task.is_due():
                    try:
                        await task.run()
                    except Exception:
                        pass
            await asyncio.sleep(self._tick_interval)

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._task = asyncio.get_event_loop().create_task(self._loop())

    def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()


_default_scheduler: Optional[CronScheduler] = None


def get_scheduler() -> CronScheduler:
    global _default_scheduler
    if _default_scheduler is None:
        _default_scheduler = CronScheduler()
    return _default_scheduler

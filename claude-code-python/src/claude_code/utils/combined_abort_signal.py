# 原始 TS: utils/combinedAbortSignal.ts
"""组合多个 asyncio.Event 为单一取消信号"""
from __future__ import annotations

import asyncio
from typing import List


class CombinedAbortSignal:
    """
    组合多个取消信号：任意一个触发则整体触发。
    类似 AbortSignal.any() 的 Python 等价。
    """

    def __init__(self, signals: List[asyncio.Event]) -> None:
        self._event = asyncio.Event()
        self._signals = signals
        self._tasks: List[asyncio.Task] = []

    async def _watch(self, signal: asyncio.Event) -> None:
        await signal.wait()
        self._event.set()

    def start(self) -> None:
        """开始监听所有信号（在事件循环中调用）"""
        loop = asyncio.get_event_loop()
        for s in self._signals:
            task = loop.create_task(self._watch(s))
            self._tasks.append(task)

    def cancel(self) -> None:
        """手动触发取消"""
        self._event.set()
        for t in self._tasks:
            t.cancel()

    @property
    def is_aborted(self) -> bool:
        return self._event.is_set()

    async def wait(self) -> None:
        await self._event.wait()


def combine_signals(*signals: asyncio.Event) -> CombinedAbortSignal:
    combined = CombinedAbortSignal(list(signals))
    combined.start()
    return combined

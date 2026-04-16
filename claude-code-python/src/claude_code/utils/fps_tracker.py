# 原始 TS: utils/fpsTracker.ts
"""帧率/性能追踪（REPL 渲染性能监控）"""
from __future__ import annotations
import time
from collections import deque
from typing import Deque


class FpsTracker:
    def __init__(self, window: int = 60) -> None:
        self._timestamps: Deque[float] = deque(maxlen=window)

    def tick(self) -> None:
        self._timestamps.append(time.monotonic())

    @property
    def fps(self) -> float:
        if len(self._timestamps) < 2:
            return 0.0
        elapsed = self._timestamps[-1] - self._timestamps[0]
        if elapsed <= 0:
            return 0.0
        return (len(self._timestamps) - 1) / elapsed

    @property
    def frame_count(self) -> int:
        return len(self._timestamps)

    def reset(self) -> None:
        self._timestamps.clear()

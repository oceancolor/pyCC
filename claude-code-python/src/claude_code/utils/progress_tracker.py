# 原始 TS: utils/progressTracker.ts
"""进度追踪（长任务进度显示）"""
from __future__ import annotations
import sys
import time
from typing import Optional


class ProgressTracker:
    def __init__(self, total: int = 0, label: str = "") -> None:
        self.total = total
        self.current = 0
        self.label = label
        self._start = time.monotonic()

    def update(self, n: int = 1) -> None:
        self.current = min(self.current + n, self.total or self.current + n)

    def set(self, n: int) -> None:
        self.current = n

    @property
    def percent(self) -> float:
        if not self.total:
            return 0.0
        return self.current / self.total * 100

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._start

    def render(self) -> str:
        if self.total:
            bar_len = 20
            filled = int(bar_len * self.current / self.total)
            bar = "█" * filled + "░" * (bar_len - filled)
            return f"{self.label} [{bar}] {self.current}/{self.total} ({self.percent:.0f}%)"
        return f"{self.label} {self.current} ({self.elapsed:.1f}s)"

    def print(self) -> None:
        sys.stdout.write(f"\r{self.render()}")
        sys.stdout.flush()

    def done(self) -> None:
        sys.stdout.write(f"\r{self.render()} ✓\n")
        sys.stdout.flush()

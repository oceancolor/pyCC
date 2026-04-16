# 原始 TS: utils/cronTasks.ts / utils/cronTasksLock.ts / utils/cronJitterConfig.ts
"""Cron 任务定义与锁"""
from __future__ import annotations
import asyncio
import os
import random
import time
from pathlib import Path
from typing import Optional


_LOCK_DIR = Path.home() / ".claude" / "locks"


class CronTaskLock:
    """文件锁，防止多实例同时执行 cron 任务"""

    def __init__(self, task_name: str) -> None:
        _LOCK_DIR.mkdir(parents=True, exist_ok=True)
        self._path = _LOCK_DIR / f"{task_name}.lock"
        self._acquired = False

    def try_acquire(self, ttl_seconds: float = 300) -> bool:
        if self._path.exists():
            # 检查是否过期
            age = time.time() - self._path.stat().st_mtime
            if age < ttl_seconds:
                return False
        try:
            self._path.write_text(str(os.getpid()))
            self._acquired = True
            return True
        except OSError:
            return False

    def release(self) -> None:
        if self._acquired:
            try:
                self._path.unlink()
            except OSError:
                pass
            self._acquired = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.release()


def get_jitter_delay(base_seconds: float, jitter_ratio: float = 0.2) -> float:
    """返回带抖动的延迟时间（避免集中触发）"""
    jitter = base_seconds * jitter_ratio * random.random()
    return base_seconds + jitter


# 默认 cron 任务定义
DEFAULT_CRON_TASKS = [
    {"name": "cleanup_sessions", "interval": 3600, "fn": "background_housekeeping.run_housekeeping"},
    {"name": "check_updates",    "interval": 86400, "fn": "auto_updater.check_for_update"},
]

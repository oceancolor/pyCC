# 原始 TS: utils/activityManager.ts
"""活动管理器：跟踪 agent 是否处于活跃状态（用于防止系统睡眠、超时检测）"""
from __future__ import annotations

import time
from typing import Optional


class ActivityManager:
    """跟踪最后活跃时间，判断 session 是否空闲"""

    def __init__(self, idle_timeout_seconds: float = 300.0) -> None:
        self._last_active = time.monotonic()
        self._idle_timeout = idle_timeout_seconds
        self._is_processing = False

    def mark_active(self) -> None:
        self._last_active = time.monotonic()
        self._is_processing = True

    def mark_idle(self) -> None:
        self._last_active = time.monotonic()
        self._is_processing = False

    @property
    def is_idle(self) -> bool:
        if self._is_processing:
            return False
        return (time.monotonic() - self._last_active) >= self._idle_timeout

    @property
    def seconds_since_active(self) -> float:
        return time.monotonic() - self._last_active

    @property
    def is_processing(self) -> bool:
        return self._is_processing


# 模块级单例
_default_manager: Optional[ActivityManager] = None


def get_activity_manager() -> ActivityManager:
    global _default_manager
    if _default_manager is None:
        _default_manager = ActivityManager()
    return _default_manager

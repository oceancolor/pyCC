# 原始 TS: utils/throttle.ts / utils/debounce.ts
"""节流和防抖"""
from __future__ import annotations
import asyncio
import time
from typing import Any, Callable, Optional


def throttle(fn: Callable, interval: float) -> Callable:
    """节流：interval 秒内最多执行一次"""
    last_call = 0.0

    def wrapper(*args, **kwargs):
        nonlocal last_call
        now = time.monotonic()
        if now - last_call >= interval:
            last_call = now
            return fn(*args, **kwargs)
    return wrapper


def debounce(fn: Callable, delay: float) -> Callable:
    """防抖：delay 秒内无新调用后执行"""
    timer: Optional[Any] = None

    def wrapper(*args, **kwargs):
        nonlocal timer
        if timer is not None:
            timer.cancel()
        loop = asyncio.get_event_loop()
        timer = loop.call_later(delay, lambda: fn(*args, **kwargs))
    return wrapper


class AsyncThrottle:
    """异步节流器"""
    def __init__(self, interval: float) -> None:
        self._interval = interval
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last = time.monotonic()

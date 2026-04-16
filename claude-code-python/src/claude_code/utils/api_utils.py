# 原始 TS: utils/api.ts
"""API 工具：请求重试、限流、错误分类"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Callable, Coroutine, Optional, Type, Tuple


class RateLimiter:
    """简单令牌桶限流器"""

    def __init__(self, rate: float, burst: int = 1) -> None:
        self._rate = rate  # tokens per second
        self._burst = burst
        self._tokens = float(burst)
        self._last = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last
        self._tokens = min(self._burst, self._tokens + elapsed * self._rate)
        self._last = now

    async def acquire(self) -> None:
        while True:
            self._refill()
            if self._tokens >= 1:
                self._tokens -= 1
                return
            await asyncio.sleep(1.0 / self._rate)


async def retry_with_backoff(
    fn: Callable[[], Coroutine[Any, Any, Any]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retriable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
) -> Any:
    """带指数退避的重试"""
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except retriable_exceptions as e:
            if attempt == max_retries:
                raise
            delay = min(base_delay * (2 ** attempt), max_delay)
            await asyncio.sleep(delay)


def is_retryable_error(exc: Exception) -> bool:
    """判断是否可重试的 API 错误"""
    msg = str(exc).lower()
    return any(kw in msg for kw in ("rate limit", "overloaded", "timeout", "529", "503", "502"))


def is_auth_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(kw in msg for kw in ("authentication", "api key", "401", "forbidden", "403"))

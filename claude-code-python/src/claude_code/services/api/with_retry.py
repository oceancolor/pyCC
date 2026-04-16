"""
API retry logic. Ported from services/api/withRetry.ts (822 lines → core retry logic).
"""
from __future__ import annotations
import asyncio
import random
from typing import Any, Callable, Optional, Set

DEFAULT_MAX_RETRIES = 10
BASE_DELAY_MS = 500
MAX_529_RETRIES = 3
FLOOR_OUTPUT_TOKENS = 3000

FOREGROUND_529_RETRY_SOURCES: Set[str] = {
    "repl_main_thread", "sdk", "agent:custom", "agent:default",
    "agent:builtin", "compact", "hook_agent", "hook_prompt",
    "verification_agent", "side_question", "auto_mode",
}

RETRYABLE_STATUS_CODES = {500, 502, 503, 529}
RETRY_ON_CONNECTION_ERROR = True


def should_retry_529(source: Optional[str]) -> bool:
    return source in FOREGROUND_529_RETRY_SOURCES


def calc_retry_delay(attempt: int, base_ms: int = BASE_DELAY_MS,
                     jitter: bool = True) -> float:
    """Exponential backoff with jitter."""
    delay_ms = base_ms * (2 ** attempt)
    if jitter:
        delay_ms = delay_ms * (0.5 + random.random() * 0.5)
    return delay_ms / 1000.0


async def with_api_retry(
    fn: Callable,
    max_retries: int = DEFAULT_MAX_RETRIES,
    source: Optional[str] = None,
    signal: Any = None,
) -> Any:
    """
    Execute fn with exponential-backoff retry on transient errors.
    Handles: 429 (rate limit), 500/502/503/529, connection errors.
    """
    last_error: Optional[Exception] = None
    count_529 = 0

    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            last_error = e
            status = getattr(e, "status_code", None) or getattr(e, "status", None)

            # Abort signal: don't retry
            if _is_abort_error(e):
                raise

            # 401: auth error, don't retry
            if status == 401:
                raise

            # 429: rate limited — retry with backoff
            if status == 429:
                if attempt >= max_retries:
                    raise
                delay = calc_retry_delay(attempt)
                await asyncio.sleep(delay)
                continue

            # 529: overloaded — only retry for foreground sources
            if status == 529:
                count_529 += 1
                if count_529 > MAX_529_RETRIES or not should_retry_529(source):
                    raise
                delay = calc_retry_delay(attempt, base_ms=2000)
                await asyncio.sleep(delay)
                continue

            # 5xx: retry
            if status in RETRYABLE_STATUS_CODES:
                if attempt >= max_retries:
                    raise
                delay = calc_retry_delay(attempt)
                await asyncio.sleep(delay)
                continue

            # Connection error: retry
            if _is_connection_error(e):
                if attempt >= max_retries:
                    raise
                delay = calc_retry_delay(attempt)
                await asyncio.sleep(delay)
                continue

            # Other: don't retry
            raise

    raise last_error or RuntimeError("Max retries exceeded")


def _is_abort_error(e: Exception) -> bool:
    return type(e).__name__ in ("APIUserAbortError", "CancelledError") or \
           isinstance(e, asyncio.CancelledError)


def _is_connection_error(e: Exception) -> bool:
    return type(e).__name__ in ("APIConnectionError", "ConnectionError",
                                 "aiohttp.ClientConnectionError") or \
           "connection" in str(type(e).__name__).lower()

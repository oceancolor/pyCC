"""
API retry logic. Ported from services/api/withRetry.ts (822 lines).
"""
from __future__ import annotations

import asyncio
import os
import random
import re
from typing import Any, AsyncGenerator, Callable, Dict, Optional, Set, TypedDict

DEFAULT_MAX_RETRIES = 10
BASE_DELAY_MS = 500
MAX_529_RETRIES = 3
FLOOR_OUTPUT_TOKENS = 3000

FOREGROUND_529_RETRY_SOURCES: Set[str] = {
    "repl_main_thread",
    "repl_main_thread:outputStyle:custom",
    "repl_main_thread:outputStyle:Explanatory",
    "repl_main_thread:outputStyle:Learning",
    "sdk",
    "agent:custom",
    "agent:default",
    "agent:builtin",
    "compact",
    "hook_agent",
    "hook_prompt",
    "verification_agent",
    "side_question",
    "auto_mode",
}

RETRYABLE_STATUS_CODES = {408, 409, 500, 502, 503, 529}
RETRY_ON_CONNECTION_ERROR = True


class RetryContext(TypedDict, total=False):
    """Retry context passed to operation callable."""
    max_tokens_override: Optional[int]
    model: str
    thinking_config: Dict[str, Any]
    fast_mode: Optional[bool]


class CannotRetryError(Exception):
    """Raised when retries are exhausted or the error is non-retryable."""

    def __init__(self, original_error: Exception, retry_context: RetryContext) -> None:
        message = str(original_error)
        super().__init__(message)
        self.name = "RetryError"
        self.original_error = original_error
        self.retry_context = retry_context
        # Preserve original stack trace
        if original_error.__traceback__:
            self.__traceback__ = original_error.__traceback__


class FallbackTriggeredError(Exception):
    """Raised when model fallback is triggered after repeated 529 errors."""

    def __init__(self, original_model: str, fallback_model: str) -> None:
        super().__init__(
            f"Model fallback triggered: {original_model} -> {fallback_model}"
        )
        self.name = "FallbackTriggeredError"
        self.original_model = original_model
        self.fallback_model = fallback_model


def should_retry_529(source: Optional[str]) -> bool:
    """True if this query source should retry on 529 (overloaded).
    
    None → retry (conservative for untagged call paths).
    """
    if source is None:
        return True
    return source in FOREGROUND_529_RETRY_SOURCES


def get_retry_delay(
    attempt: int,
    retry_after_header: Optional[str] = None,
    max_delay_ms: int = 32000,
) -> float:
    """Calculate retry delay in milliseconds with exponential backoff + jitter.

    Ported from getRetryDelay (TS line 530).
    """
    if retry_after_header:
        try:
            seconds = int(retry_after_header)
            return float(seconds * 1000)
        except (ValueError, TypeError):
            pass

    base_delay = min(BASE_DELAY_MS * (2 ** (attempt - 1)), max_delay_ms)
    jitter = random.random() * 0.25 * base_delay
    return base_delay + jitter


def parse_max_tokens_context_overflow_error(
    error: Exception,
) -> Optional[Dict[str, int]]:
    """Parse context overflow error to extract token counts.

    Returns dict with inputTokens, maxTokens, contextLimit or None.
    Ported from parseMaxTokensContextOverflowError (TS line 550).
    """
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    message = str(error)

    if status != 400 or not message:
        return None

    if "input length and `max_tokens` exceed context limit" not in message:
        return None

    # Example: "input length and `max_tokens` exceed context limit: 188059 + 20000 > 200000"
    pattern = r"input length and `max_tokens` exceed context limit: (\d+) \+ (\d+) > (\d+)"
    match = re.search(pattern, message)
    if not match or len(match.groups()) != 3:
        return None

    try:
        input_tokens = int(match.group(1))
        max_tokens = int(match.group(2))
        context_limit = int(match.group(3))
    except (ValueError, AttributeError):
        return None

    return {
        "inputTokens": input_tokens,
        "maxTokens": max_tokens,
        "contextLimit": context_limit,
    }


def is_529_error(error: Exception) -> bool:
    """Check if the error is a 529 (overloaded) error.

    Ported from is529Error (TS line 610).
    Checks status code AND message content (SDK sometimes passes wrong status).
    """
    status = getattr(error, "status_code", None) or getattr(error, "status", None)

    if status == 529:
        return True

    # SDK sometimes fails to properly pass the 529 status code during streaming
    message = str(error)
    if '"type":"overloaded_error"' in message:
        return True

    return False


def get_default_max_retries() -> int:
    """Get default max retries from env or constant.

    Ported from getDefaultMaxRetries (TS line 789).
    """
    env_val = os.environ.get("CLAUDE_CODE_MAX_RETRIES")
    if env_val:
        try:
            return int(env_val)
        except (ValueError, TypeError):
            pass
    return DEFAULT_MAX_RETRIES


async def with_retry(
    fn: Callable,
    options: Optional[Dict[str, Any]] = None,
    *,
    max_retries: Optional[int] = None,
    source: Optional[str] = None,
    signal: Any = None,
    fallback_model: Optional[str] = None,
    initial_consecutive_529_errors: int = 0,
) -> AsyncGenerator[Any, None]:
    """Async generator with retry logic, exponential backoff, fallback.

    Ported from withRetry async generator (TS line 170).
    Yields SystemAPIErrorMessages during waits, returns final result.

    Usage:
        gen = with_retry(my_fn, options, source="repl_main_thread")
        result = None
        async for msg in gen:
            handle_system_message(msg)
        result = await gen.aclose()  # or catch StopAsyncIteration
    """
    if options is None:
        options = {}

    effective_max_retries = max_retries
    if effective_max_retries is None:
        effective_max_retries = options.get("max_retries", get_default_max_retries())

    retry_context: RetryContext = {
        "model": options.get("model", ""),
        "thinking_config": options.get("thinking_config", {"type": "disabled"}),
    }

    consecutive_529_errors = initial_consecutive_529_errors
    last_error: Optional[Exception] = None

    return await _with_retry_impl(
        fn=fn,
        options=options,
        max_retries=effective_max_retries,
        retry_context=retry_context,
        source=source,
        signal=signal,
        fallback_model=fallback_model,
        consecutive_529_errors=consecutive_529_errors,
    )


async def _with_retry_impl(
    fn: Callable,
    options: Dict[str, Any],
    max_retries: int,
    retry_context: RetryContext,
    source: Optional[str],
    signal: Any,
    fallback_model: Optional[str],
    consecutive_529_errors: int,
) -> Any:
    """Internal retry implementation (non-generator for simplicity)."""
    last_error: Optional[Exception] = None

    for attempt in range(1, max_retries + 2):  # 1-indexed, inclusive
        try:
            return await fn()
        except Exception as error:
            last_error = error

            # Abort/cancel — don't retry
            if _is_abort_error(error):
                raise

            # 401: auth error — don't retry
            status = _get_status(error)
            if status == 401:
                raise

            # Non-foreground sources bail immediately on 529
            if is_529_error(error) and not should_retry_529(source):
                raise CannotRetryError(error, retry_context)

            # Track consecutive 529 errors and potentially trigger fallback
            if is_529_error(error):
                consecutive_529_errors += 1
                if consecutive_529_errors >= MAX_529_RETRIES:
                    if fallback_model:
                        raise FallbackTriggeredError(
                            retry_context.get("model", ""),
                            fallback_model,
                        )
                    # Check for CannotRetry on repeated 529
                    if os.environ.get("USER_TYPE") == "external":
                        raise CannotRetryError(error, retry_context)

            # Context overflow — adjust max_tokens for next attempt
            if status == 400:
                overflow_data = parse_max_tokens_context_overflow_error(error)
                if overflow_data:
                    input_tokens = overflow_data["inputTokens"]
                    context_limit = overflow_data["contextLimit"]
                    safety_buffer = 1000
                    available_context = max(
                        0, context_limit - input_tokens - safety_buffer
                    )
                    if available_context < FLOOR_OUTPUT_TOKENS:
                        raise  # Not recoverable

                    thinking_config = retry_context.get("thinking_config", {})
                    min_required = (
                        thinking_config.get("budgetTokens", 0)
                        if thinking_config.get("type") == "enabled"
                        else 0
                    ) + 1
                    adjusted_max_tokens = max(
                        FLOOR_OUTPUT_TOKENS, available_context, min_required
                    )
                    retry_context["max_tokens_override"] = adjusted_max_tokens
                    continue

            # Exhausted retries
            if attempt > max_retries:
                raise CannotRetryError(error, retry_context)

            # Check if this error type is retryable
            if not _should_retry(error):
                raise CannotRetryError(error, retry_context)

            # Calculate delay
            retry_after = _get_retry_after_header(error)
            delay_ms = get_retry_delay(attempt, retry_after)

            await asyncio.sleep(delay_ms / 1000.0)

    raise CannotRetryError(
        last_error or RuntimeError("Max retries exceeded"), retry_context
    )


def calc_retry_delay(
    attempt: int, base_ms: int = BASE_DELAY_MS, jitter: bool = True
) -> float:
    """Exponential backoff with jitter. Returns seconds."""
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
            status = _get_status(e)

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
            if status == 529 or is_529_error(e):
                count_529 += 1
                if count_529 > MAX_529_RETRIES or not should_retry_529(source):
                    raise
                delay = calc_retry_delay(attempt, base_ms=2000)
                await asyncio.sleep(delay)
                continue

            # 5xx / other retryable: retry
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_status(e: Exception) -> Optional[int]:
    """Extract HTTP status code from exception."""
    return getattr(e, "status_code", None) or getattr(e, "status", None)


def _get_retry_after_header(e: Exception) -> Optional[str]:
    """Extract Retry-After header value from exception."""
    headers = getattr(e, "headers", None)
    if headers is None:
        return None
    if hasattr(headers, "get"):
        return headers.get("retry-after") or headers.get("Retry-After")
    if isinstance(headers, dict):
        return headers.get("retry-after") or headers.get("Retry-After")
    return None


def _is_abort_error(e: Exception) -> bool:
    return (
        type(e).__name__ in ("APIUserAbortError", "CancelledError")
        or isinstance(e, asyncio.CancelledError)
    )


def _is_connection_error(e: Exception) -> bool:
    return type(e).__name__ in (
        "APIConnectionError",
        "ConnectionError",
        "aiohttp.ClientConnectionError",
    ) or "connection" in type(e).__name__.lower()


def _should_retry(error: Exception) -> bool:
    """Determine if the error is retryable."""
    status = _get_status(error)

    if _is_connection_error(error):
        return True

    if status is None:
        return False

    # Retry on request timeouts
    if status == 408:
        return True

    # Retry on lock timeouts
    if status == 409:
        return True

    # Retry on rate limits
    if status == 429:
        return True

    # Retry on 529 (overloaded)
    if status == 529 or is_529_error(error):
        return True

    # Retry on 5xx server errors
    if status >= 500:
        return True

    return False

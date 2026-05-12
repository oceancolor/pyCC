"""
API retry logic. Ported from services/api/withRetry.ts (822 lines).

Key changes from TS:
- withRetry() is an async generator: yields SystemAPIErrorMessage during waits,
  returns final value T via StopAsyncIteration.value (Python 3.10+).
- CannotRetryError / FallbackTriggeredError are Exception subclasses (no 'name' attr
  on the class but stored as an instance attribute for compatibility).
"""
from __future__ import annotations

import asyncio
import os
import random
import re
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    Optional,
    Set,
    Tuple,
    TypedDict,
)

DEFAULT_MAX_RETRIES = 10
BASE_DELAY_MS = 500
MAX_529_RETRIES = 3
FLOOR_OUTPUT_TOKENS = 3000

# Foreground query sources where the user IS blocking on the result — these
# retry on 529.  Everything else bails immediately to avoid retry amplification.
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

# Persistent-retry constants (unattended/ant mode)
PERSISTENT_MAX_BACKOFF_MS = 5 * 60 * 1000   # 5 min
PERSISTENT_RESET_CAP_MS   = 6 * 60 * 60 * 1000  # 6 hr
HEARTBEAT_INTERVAL_MS     = 30_000

# Fast-mode cooldown thresholds
DEFAULT_FAST_MODE_FALLBACK_HOLD_MS = 30 * 60 * 1000  # 30 min
SHORT_RETRY_THRESHOLD_MS           = 20 * 1000        # 20 s
MIN_COOLDOWN_MS                    = 10 * 60 * 1000   # 10 min


# ---------------------------------------------------------------------------
# TypedDicts / data classes
# ---------------------------------------------------------------------------

class RetryContext(TypedDict, total=False):
    """Mirrors TS RetryContext interface."""
    max_tokens_override: Optional[int]
    model: str
    thinking_config: Dict[str, Any]
    fast_mode: Optional[bool]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CannotRetryError(Exception):
    """Raised when retries are exhausted or the error is non-retryable.

    Mirrors CannotRetryError in withRetry.ts.
    """

    def __init__(self, original_error: Exception, retry_context: "RetryContext") -> None:
        message = str(original_error)
        super().__init__(message)
        self.name = "RetryError"
        self.original_error = original_error
        self.retry_context = retry_context
        # Preserve original stack trace when available
        if isinstance(original_error, Exception) and original_error.__traceback__:
            self.__traceback__ = original_error.__traceback__


class FallbackTriggeredError(Exception):
    """Raised when model fallback is triggered after repeated 529 errors.

    Mirrors FallbackTriggeredError in withRetry.ts.
    """

    def __init__(self, original_model: str, fallback_model: str) -> None:
        super().__init__(
            f"Model fallback triggered: {original_model} -> {fallback_model}"
        )
        self.name = "FallbackTriggeredError"
        self.original_model = original_model
        self.fallback_model = fallback_model


# ---------------------------------------------------------------------------
# Core predicates
# ---------------------------------------------------------------------------

def should_retry_529(source: Optional[str]) -> bool:
    """True if this query source should retry on 529 (overloaded).

    None → retry (conservative: unknown paths are treated as foreground).
    Mirrors shouldRetry529 in withRetry.ts.
    """
    if source is None:
        return True
    return source in FOREGROUND_529_RETRY_SOURCES


def is_529_error(error: Exception) -> bool:
    """Check if the error is a 529 (overloaded) error.

    Mirrors is529Error in withRetry.ts.
    The SDK sometimes fails to properly pass the 529 status code during streaming,
    so we also check the message content.
    """
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    if status == 529:
        return True
    message = str(error)
    if '"type":"overloaded_error"' in message:
        return True
    return False


# ---------------------------------------------------------------------------
# Delay helpers
# ---------------------------------------------------------------------------

def get_retry_delay(
    attempt: int,
    retry_after_header: Optional[str] = None,
    max_delay_ms: int = 32_000,
) -> float:
    """Calculate retry delay in milliseconds with exponential backoff + jitter.

    Mirrors getRetryDelay in withRetry.ts.

    Args:
        attempt:            1-indexed attempt number.
        retry_after_header: Value of the Retry-After header (seconds string).
        max_delay_ms:       Maximum delay cap in milliseconds.

    Returns:
        Delay in milliseconds.
    """
    if retry_after_header:
        try:
            seconds = int(retry_after_header)
            return float(seconds * 1_000)
        except (ValueError, TypeError):
            pass

    base_delay = min(BASE_DELAY_MS * (2 ** (attempt - 1)), max_delay_ms)
    jitter = random.random() * 0.25 * base_delay
    return base_delay + jitter


def calc_retry_delay(
    attempt: int, base_ms: int = BASE_DELAY_MS, jitter: bool = True
) -> float:
    """Exponential backoff helper. Returns delay in *seconds*.

    Kept for backward-compatibility with callers that used this name.
    """
    delay_ms = base_ms * (2 ** attempt)
    if jitter:
        delay_ms = delay_ms * (0.5 + random.random() * 0.5)
    return delay_ms / 1_000.0


def get_default_max_retries() -> int:
    """Get default max retries from env or constant.

    Mirrors getDefaultMaxRetries in withRetry.ts.
    """
    env_val = os.environ.get("CLAUDE_CODE_MAX_RETRIES")
    if env_val:
        try:
            return int(env_val)
        except (ValueError, TypeError):
            pass
    return DEFAULT_MAX_RETRIES


# ---------------------------------------------------------------------------
# Context-overflow parser
# ---------------------------------------------------------------------------

def parse_max_tokens_context_overflow_error(
    error: Exception,
) -> Optional[Dict[str, int]]:
    """Parse context overflow error to extract token counts.

    Returns dict with inputTokens, maxTokens, contextLimit or None.
    Mirrors parseMaxTokensContextOverflowError in withRetry.ts.
    """
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    message = str(error)

    if status != 400 or not message:
        return None

    if "input length and `max_tokens` exceed context limit" not in message:
        return None

    # e.g. "input length and `max_tokens` exceed context limit: 188059 + 20000 > 200000"
    pattern = (
        r"input length and `max_tokens` exceed context limit: (\d+) \+ (\d+) > (\d+)"
    )
    match = re.search(pattern, message)
    if not match or len(match.groups()) != 3:
        return None

    try:
        input_tokens  = int(match.group(1))
        max_tokens    = int(match.group(2))
        context_limit = int(match.group(3))
    except (ValueError, AttributeError):
        return None

    return {
        "inputTokens":  input_tokens,
        "maxTokens":    max_tokens,
        "contextLimit": context_limit,
    }


# ---------------------------------------------------------------------------
# Main async-generator withRetry
# ---------------------------------------------------------------------------

class _RetryResult:
    """Sentinel yielded by _with_retry_generator to carry the final result.

    Python async generators cannot return values like TS async generators can.
    We yield this sentinel as the *last* item so callers can distinguish
    progress messages from the final result::

        async for item in with_retry(...):
            if isinstance(item, _RetryResult):
                result = item.value
            else:
                handle_system_message(item)  # retry-wait notification
    """
    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value


async def with_retry(
    get_client: Callable[[], Any],
    operation: Callable[[Any, int, "RetryContext"], Any],
    options: Optional[Dict[str, Any]] = None,
    *,
    # Legacy / simplified call signature (no explicit get_client / operation split)
    fn: Optional[Callable[[], Any]] = None,
    max_retries: Optional[int] = None,
    source: Optional[str] = None,
    signal: Any = None,
    fallback_model: Optional[str] = None,
    initial_consecutive_529_errors: int = 0,
) -> Any:
    """Execute operation with retry logic, exponential backoff and model fallback.

    Mirrors withRetry<T> async generator in withRetry.ts.

    This coroutine returns the final result of *operation*.  It accepts an
    optional ``on_retry_message`` callback to receive SystemAPIErrorMessage
    dicts that the TS version would yield during retry waits.

    For full async-generator semantics (yielding messages) use the lower-level
    ``_with_retry_generator`` directly.

    Two call signatures are supported:

    1. TS-faithful (get_client + operation function)::

           result = await with_retry(get_client, operation, options)

    2. Simplified (fn-only, backwards-compat)::

           result = await with_retry(
               lambda: None, lambda c,a,ctx: None,
               fn=my_coro_factory, source="..."
           )
    """
    if options is None:
        options = {}

    effective_max_retries = max_retries
    if effective_max_retries is None:
        effective_max_retries = options.get("max_retries") or get_default_max_retries()

    retry_context: RetryContext = {
        "model":          options.get("model", ""),
        "thinking_config": options.get("thinking_config", {"type": "disabled"}),
    }

    if options.get("fast_mode") is not None:
        retry_context["fast_mode"] = options.get("fast_mode")

    _source         = source or options.get("query_source")
    _signal         = signal or options.get("signal")
    _fallback_model = fallback_model or options.get("fallback_model")
    _init_529       = initial_consecutive_529_errors or options.get(
        "initial_consecutive_529_errors", 0
    )

    async for item in _with_retry_generator(
        get_client=get_client,
        operation=operation,
        fn=fn,
        options=options,
        max_retries=effective_max_retries,
        retry_context=retry_context,
        source=_source,
        signal=_signal,
        fallback_model=_fallback_model,
        initial_consecutive_529_errors=_init_529,
    ):
        if isinstance(item, _RetryResult):
            return item.value
        # System retry message — callers who need them should use the generator directly

    # Should not be reached: generator always yields _RetryResult or raises
    raise CannotRetryError(RuntimeError("with_retry: generator ended without result"), retry_context)


async def _with_retry_generator(
    get_client: Callable[[], Any],
    operation: Callable[[Any, int, "RetryContext"], Any],
    fn: Optional[Callable[[], Any]],
    options: Dict[str, Any],
    max_retries: int,
    retry_context: "RetryContext",
    source: Optional[str],
    signal: Any,
    fallback_model: Optional[str],
    initial_consecutive_529_errors: int,
) -> "AsyncGenerator[Any, None]":
    """Internal async generator implementation.

    Yields SystemAPIErrorMessage dicts during retry sleeps, then yields a
    ``_RetryResult`` sentinel carrying the final result value.
    On unrecoverable error raises CannotRetryError / FallbackTriggeredError.
    """
    client: Any = None
    consecutive_529_errors = initial_consecutive_529_errors
    last_error: Optional[Exception] = None
    persistent_attempt = 0
    persistent = _is_persistent_retry_enabled()

    for attempt in range(1, max_retries + 2):  # inclusive of max_retries+1
        # Respect abort signal before each attempt
        if signal is not None and getattr(signal, "aborted", False):
            raise _abort_error()

        try:
            # Get/refresh client when needed
            if client is None or _needs_client_refresh(last_error):
                if asyncio.iscoroutinefunction(get_client):
                    client = await get_client()
                else:
                    client = get_client()

            # Execute operation — success path: yield _RetryResult then stop
            if fn is not None:
                # Simplified path: fn() is a coroutine factory
                raw = fn()
                if asyncio.iscoroutine(raw):
                    _result = await raw
                else:
                    _result = raw
            elif asyncio.iscoroutinefunction(operation):
                _result = await operation(client, attempt, retry_context)
            else:
                _result = operation(client, attempt, retry_context)
            # Successful: emit sentinel and stop
            yield _RetryResult(_result)
            return

        except Exception as error:
            last_error = error

            # Abort signal: never retry
            if _is_abort_error(error):
                raise

            status = _get_status(error)

            # 401 auth error: don't retry in normal mode
            # (but do in CCR/remote mode — see TS shouldRetry logic)
            _is_remote = bool(os.environ.get("CLAUDE_CODE_REMOTE"))
            if status == 401 and not _is_remote:
                raise

            # Non-foreground sources bail on 529 immediately
            if is_529_error(error) and not should_retry_529(source):
                raise CannotRetryError(error, retry_context)

            # Track consecutive 529 errors; trigger fallback after threshold
            if is_529_error(error):
                consecutive_529_errors += 1
                if consecutive_529_errors >= MAX_529_RETRIES:
                    if fallback_model:
                        raise FallbackTriggeredError(
                            retry_context.get("model", ""),
                            fallback_model,
                        )
                    if (
                        os.environ.get("USER_TYPE") == "external"
                        and not os.environ.get("IS_SANDBOX")
                        and not persistent
                    ):
                        raise CannotRetryError(error, retry_context)

            # Persistent retry: 429/529 loop indefinitely
            _is_transient_capacity = is_529_error(error) or status == 429
            if attempt > max_retries and not (persistent and _is_transient_capacity):
                raise CannotRetryError(error, retry_context)

            # Handle Bedrock/GCP/AWS credential errors (always retryable)
            _cloud_auth = _handle_cloud_auth_error(error)

            # Determine retryability for non-cloud errors
            if not _cloud_auth and not _should_retry(error):
                raise CannotRetryError(error, retry_context)

            # Context overflow: adjust max_tokens for next attempt (TS lines 400-430)
            if status == 400:
                overflow_data = parse_max_tokens_context_overflow_error(error)
                if overflow_data:
                    input_tokens  = overflow_data["inputTokens"]
                    context_limit = overflow_data["contextLimit"]
                    safety_buffer = 1_000
                    available_context = max(0, context_limit - input_tokens - safety_buffer)
                    if available_context < FLOOR_OUTPUT_TOKENS:
                        raise error

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
                    continue  # retry immediately with new max_tokens

            # Calculate retry delay
            retry_after = _get_retry_after_header(error)

            if persistent and _is_transient_capacity:
                persistent_attempt += 1
                reset_delay = _get_rate_limit_reset_delay_ms(error)
                if status == 429 and reset_delay is not None:
                    delay_ms = reset_delay
                else:
                    delay_ms = min(
                        get_retry_delay(persistent_attempt, retry_after, PERSISTENT_MAX_BACKOFF_MS),
                        PERSISTENT_RESET_CAP_MS,
                    )
            else:
                delay_ms = get_retry_delay(attempt, retry_after)

            # Yield SystemAPIErrorMessage(s) so callers can surface progress
            reported_attempt = persistent_attempt if persistent else attempt
            if persistent and delay_ms > HEARTBEAT_INTERVAL_MS:
                # Chunk long sleeps with heartbeat yields
                remaining = delay_ms
                while remaining > 0:
                    if signal is not None and getattr(signal, "aborted", False):
                        raise _abort_error()
                    error_msg = _create_system_api_error_message(
                        error, remaining, reported_attempt, max_retries
                    )
                    if error_msg is not None:
                        yield error_msg
                    chunk = min(remaining, HEARTBEAT_INTERVAL_MS)
                    await asyncio.sleep(chunk / 1_000.0)
                    remaining -= chunk
                    if persistent and attempt >= max_retries:
                        attempt = max_retries  # clamp
            else:
                error_msg = _create_system_api_error_message(
                    error, delay_ms, reported_attempt, max_retries
                )
                if error_msg is not None:
                    yield error_msg
                await asyncio.sleep(delay_ms / 1_000.0)

    raise CannotRetryError(
        last_error or RuntimeError("Max retries exceeded"), retry_context
    )


# ---------------------------------------------------------------------------
# Simplified withApiRetry (convenience wrapper)
# ---------------------------------------------------------------------------

async def with_api_retry(
    fn: Callable[[], Any],
    max_retries: int = DEFAULT_MAX_RETRIES,
    source: Optional[str] = None,
    signal: Any = None,
) -> Any:
    """
    Execute fn with exponential-backoff retry on transient errors.
    Handles: 429 (rate limit), 500/502/503/529, connection errors.

    This is a simplified non-generator wrapper.  For the full TS-faithful
    generator (with SystemAPIErrorMessage yields) use with_retry().
    """
    last_error: Optional[Exception] = None
    count_529 = 0

    for attempt in range(max_retries + 1):
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                return await result
            return result
        except Exception as e:
            last_error = e
            status = _get_status(e)

            # Abort signal: don't retry
            if _is_abort_error(e):
                raise

            # 401: auth error, don't retry
            if status == 401:
                raise

            # 529: overloaded — only retry for foreground sources
            if status == 529 or is_529_error(e):
                count_529 += 1
                if count_529 > MAX_529_RETRIES or not should_retry_529(source):
                    raise
                delay = calc_retry_delay(attempt, base_ms=2_000)
                await asyncio.sleep(delay)
                continue

            # 429: rate limited
            if status == 429:
                if attempt >= max_retries:
                    raise
                delay = calc_retry_delay(attempt)
                await asyncio.sleep(delay)
                continue

            # Retryable 5xx / connection errors
            if status in RETRYABLE_STATUS_CODES:
                if attempt >= max_retries:
                    raise
                delay = calc_retry_delay(attempt)
                await asyncio.sleep(delay)
                continue

            if _is_connection_error(e):
                if attempt >= max_retries:
                    raise
                delay = calc_retry_delay(attempt)
                await asyncio.sleep(delay)
                continue

            # Not retryable
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
        val = headers.get("retry-after") or headers.get("Retry-After")
        return val
    if isinstance(headers, dict):
        return headers.get("retry-after") or headers.get("Retry-After")
    return None


def _get_rate_limit_reset_delay_ms(e: Exception) -> Optional[float]:
    """Parse anthropic-ratelimit-unified-reset header → delay in ms."""
    headers = getattr(e, "headers", None)
    if headers is None:
        return None
    if hasattr(headers, "get"):
        reset_header = headers.get("anthropic-ratelimit-unified-reset")
    elif isinstance(headers, dict):
        reset_header = headers.get("anthropic-ratelimit-unified-reset")
    else:
        return None
    if not reset_header:
        return None
    try:
        reset_unix_sec = float(reset_header)
    except (ValueError, TypeError):
        return None
    import time
    delay_ms = reset_unix_sec * 1_000 - time.time() * 1_000
    if delay_ms <= 0:
        return None
    return min(delay_ms, PERSISTENT_RESET_CAP_MS)


def _is_abort_error(e: Exception) -> bool:
    return (
        type(e).__name__ in ("APIUserAbortError", "CancelledError")
        or isinstance(e, asyncio.CancelledError)
    )


def _is_connection_error(e: Exception) -> bool:
    type_name = type(e).__name__
    return type_name in (
        "APIConnectionError",
        "ConnectionError",
    ) or "connection" in type_name.lower()


def _is_persistent_retry_enabled() -> bool:
    """Check CLAUDE_CODE_UNATTENDED_RETRY env flag."""
    val = os.environ.get("CLAUDE_CODE_UNATTENDED_RETRY", "").strip().lower()
    return val in ("1", "true", "yes")


def _is_stale_connection_error(e: Exception) -> bool:
    """True for ECONNRESET/EPIPE connection errors."""
    if not _is_connection_error(e):
        return False
    # Try to get the error code
    cause = getattr(e, "__cause__", None) or getattr(e, "args", (None,))[0]
    code = getattr(cause, "errno", None) or getattr(e, "errno", None)
    # ECONNRESET=104, EPIPE=32 on Linux; also check string
    msg = str(e)
    return (
        code in (32, 104)
        or "ECONNRESET" in msg
        or "EPIPE" in msg
    )


def _needs_client_refresh(last_error: Optional[Exception]) -> bool:
    """True when a fresh client should be obtained before the next attempt."""
    if last_error is None:
        return False
    status = _get_status(last_error)
    if status == 401:
        return True
    if _is_stale_connection_error(last_error):
        return True
    return False


def _should_retry(error: Exception) -> bool:
    """Determine if the error is retryable.

    Mirrors shouldRetry(error: APIError) in withRetry.ts, adapted for Python.
    """
    status = _get_status(error)

    if _is_connection_error(error):
        return True

    if status is None:
        return False

    # x-should-retry header check
    headers = getattr(error, "headers", None)
    should_retry_header: Optional[str] = None
    if headers is not None:
        if hasattr(headers, "get"):
            should_retry_header = (
                headers.get("x-should-retry") or
                headers.get("X-Should-Retry")
            )
        elif isinstance(headers, dict):
            should_retry_header = (
                headers.get("x-should-retry") or
                headers.get("X-Should-Retry")
            )

    is_subscriber = _is_claude_ai_subscriber()
    is_enterprise = _is_enterprise_subscriber()

    if should_retry_header == "true" and (not is_subscriber or is_enterprise):
        return True
    if should_retry_header == "false":
        is_5xx = status is not None and status >= 500
        is_ant  = os.environ.get("USER_TYPE") == "ant"
        if not (is_ant and is_5xx):
            return False

    # Overloaded error in message body (streaming quirk)
    msg = str(error)
    if '"type":"overloaded_error"' in msg:
        return True

    # Context overflow — handled separately but also retryable
    if status == 400 and parse_max_tokens_context_overflow_error(error):
        return True

    # Request timeout
    if status == 408:
        return True
    # Lock timeout
    if status == 409:
        return True
    # Rate limit — retryable unless subscriber (non-enterprise)
    if status == 429:
        return not is_subscriber or is_enterprise
    # Auth — allow one retry to get a fresh token
    if status == 401:
        return True
    # Server errors
    if status >= 500:
        return True

    return False


def _handle_cloud_auth_error(error: Exception) -> bool:
    """Clear cloud credential caches on auth errors.

    Mirrors handleAwsCredentialError + handleGcpCredentialError.
    Returns True if action was taken (meaning error is retryable).
    """
    # Bedrock
    use_bedrock = bool(os.environ.get("CLAUDE_CODE_USE_BEDROCK"))
    if use_bedrock:
        status = _get_status(error)
        type_name = type(error).__name__
        if type_name == "CredentialsProviderError" or status == 403:
            # Clear cache (try if module available)
            try:
                from claude_code.utils.auth import clear_aws_credentials_cache
                clear_aws_credentials_cache()
            except Exception:
                pass
            return True

    # Vertex
    use_vertex = bool(os.environ.get("CLAUDE_CODE_USE_VERTEX"))
    if use_vertex:
        status = _get_status(error)
        msg = str(error)
        google_auth_fail = (
            "Could not load the default credentials" in msg
            or "Could not refresh access token" in msg
            or "invalid_grant" in msg
        )
        if google_auth_fail or status == 401:
            try:
                from claude_code.utils.auth import clear_gcp_credentials_cache
                clear_gcp_credentials_cache()
            except Exception:
                pass
            return True

    return False


def _is_claude_ai_subscriber() -> bool:
    """Check if running as a ClaudeAI subscriber."""
    try:
        from claude_code.utils.auth import is_claude_ai_subscriber
        return is_claude_ai_subscriber()
    except Exception:
        return False


def _is_enterprise_subscriber() -> bool:
    """Check if running as an enterprise subscriber."""
    try:
        from claude_code.utils.auth import is_enterprise_subscriber
        return is_enterprise_subscriber()
    except Exception:
        return False


def _abort_error() -> Exception:
    """Create an abort/cancellation error."""
    try:
        from anthropic import APIUserAbortError
        return APIUserAbortError()
    except Exception:
        return asyncio.CancelledError()


def _create_system_api_error_message(
    error: Exception,
    remaining_ms: float,
    attempt: int,
    max_retries: int,
) -> Optional[Dict[str, Any]]:
    """Create a SystemAPIErrorMessage dict for retry-wait notification.

    Mirrors createSystemAPIErrorMessage from src/utils/messages.ts.
    Returns None if the module is unavailable.
    """
    try:
        from claude_code.utils.messages import create_system_api_error_message
        return create_system_api_error_message(error, remaining_ms, attempt, max_retries)
    except Exception:
        pass
    # Fallback: minimal dict
    return {
        "type": "system",
        "subtype": "api_retry",
        "error": str(error),
        "remaining_ms": remaining_ms,
        "attempt": attempt,
        "max_retries": max_retries,
    }

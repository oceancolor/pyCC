"""
AutoCompact service.
Ported from services/compact/autoCompact.ts

Provides auto-compaction logic: threshold calculation, warning-state helpers,
and the main autoCompactIfNeeded() entry point.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Optional imports with graceful fallback
# ---------------------------------------------------------------------------
try:
    from claude_code.utils.env_utils import is_env_truthy  # type: ignore
except ImportError:
    def is_env_truthy(val: Any) -> bool:  # type: ignore[misc]
        if isinstance(val, bool):
            return val
        if val is None:
            return False
        return str(val).lower() in ("1", "true", "yes")

try:
    from claude_code.utils.config import get_global_config  # type: ignore
except ImportError:
    def get_global_config() -> Any:  # type: ignore[misc]
        class _Cfg:
            autoCompactEnabled = True
        return _Cfg()

try:
    from claude_code.utils.context import get_context_window_for_model  # type: ignore
except ImportError:
    def get_context_window_for_model(model: str, betas: Any = None) -> int:  # type: ignore[misc]
        return 200_000

try:
    from claude_code.utils.debug import log_for_debugging  # type: ignore
except ImportError:
    def log_for_debugging(msg: str, **kwargs: Any) -> None:  # type: ignore[misc]
        pass

try:
    from claude_code.utils.errors import has_exact_error_message  # type: ignore
except ImportError:
    def has_exact_error_message(exc: BaseException, msg: str) -> bool:  # type: ignore[misc]
        return str(exc) == msg

try:
    from claude_code.utils.log import log_error  # type: ignore
except ImportError:
    def log_error(exc: Any) -> None:  # type: ignore[misc]
        pass

try:
    from claude_code.utils.tokens import token_count_with_estimation  # type: ignore
except (ImportError, SyntaxError):
    try:
        from claude_code.services.compact.compact import token_count_with_estimation  # type: ignore
    except (ImportError, SyntaxError):
        def token_count_with_estimation(messages: List[Dict[str, Any]]) -> int:  # type: ignore[misc]
            total = 0
            for m in messages:
                content = str(m.get("message", {}).get("content", ""))
                total += max(1, len(content) // 4)
            return total

try:
    from claude_code.services.analytics.growthbook import (  # type: ignore
        get_feature_value_cached_may_be_stale as _get_feature_value,
    )
except ImportError:
    def _get_feature_value(key: str, default: Any) -> Any:  # type: ignore[misc]
        return default

try:
    from claude_code.services.api.claude import get_max_output_tokens_for_model  # type: ignore
except (ImportError, SyntaxError):
    def get_max_output_tokens_for_model(model: str) -> int:  # type: ignore[misc]
        return 8192

try:
    from claude_code.services.api.prompt_cache_break_detection import notify_compaction  # type: ignore
except (ImportError, SyntaxError):
    def notify_compaction(source: str, agent_id: Any = None) -> None:  # type: ignore[misc]
        pass

try:
    from claude_code.services.session_memory.session_memory_utils import (  # type: ignore
        set_last_summarized_message_id,
    )
except ImportError:
    def set_last_summarized_message_id(uid: Any) -> None:  # type: ignore[misc]
        pass

try:
    from claude_code.services.compact.compact import (  # type: ignore
        CompactionResult,
        RecompactionInfo,
        compact_conversation,
        ERROR_MESSAGE_USER_ABORT,
    )
except ImportError:
    CompactionResult = Dict  # type: ignore[misc,assignment]
    RecompactionInfo = Dict  # type: ignore[misc,assignment]

    async def compact_conversation(*args: Any, **kwargs: Any) -> Any:  # type: ignore[misc]
        raise NotImplementedError("compact_conversation not available")

    ERROR_MESSAGE_USER_ABORT = "API Error: Request was aborted."

try:
    from claude_code.services.compact.post_compact_cleanup import run_post_compact_cleanup  # type: ignore
except ImportError:
    def run_post_compact_cleanup(query_source: Any = None) -> None:  # type: ignore[misc]
        pass

try:
    from claude_code.services.compact.session_memory_compact import (  # type: ignore
        try_session_memory_compaction,
    )
except ImportError:
    async def try_session_memory_compaction(  # type: ignore[misc]
        messages: List[Dict[str, Any]],
        agent_id: Any = None,
        auto_compact_threshold: Optional[int] = None,
    ) -> Optional[Any]:
        return None

try:
    from claude_code.bootstrap.state import (  # type: ignore
        mark_post_compaction,
        get_sdk_betas,
    )
except ImportError:
    def mark_post_compaction() -> None:  # type: ignore[misc]
        pass

    def get_sdk_betas() -> Optional[list]:  # type: ignore[misc]
        return None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Reserve tokens for output during compaction (p99.99 of compact summary ≈ 17,387)
MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000

AUTOCOMPACT_BUFFER_TOKENS = 13_000
WARNING_THRESHOLD_BUFFER_TOKENS = 20_000
ERROR_THRESHOLD_BUFFER_TOKENS = 20_000
MANUAL_COMPACT_BUFFER_TOKENS = 3_000

# Circuit breaker: stop retrying after this many consecutive failures
MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3


# ---------------------------------------------------------------------------
# Context-window helpers
# ---------------------------------------------------------------------------

def get_effective_context_window_size(model: str) -> int:
    """
    Returns the context window size minus the max output tokens reserved for
    the compaction summary.
    Ported from getEffectiveContextWindowSize().
    """
    reserved = min(
        get_max_output_tokens_for_model(model),
        MAX_OUTPUT_TOKENS_FOR_SUMMARY,
    )
    context_window = get_context_window_for_model(model, get_sdk_betas())

    # Allow env-var override for testing
    auto_compact_window = os.environ.get("CLAUDE_CODE_AUTO_COMPACT_WINDOW")
    if auto_compact_window:
        try:
            parsed = int(auto_compact_window)
            if parsed > 0:
                context_window = min(context_window, parsed)
        except ValueError:
            pass

    return context_window - reserved


def get_auto_compact_threshold(model: str) -> int:
    """
    Returns the token count at which autocompact should fire.
    Ported from getAutoCompactThreshold().
    """
    effective_window = get_effective_context_window_size(model)
    threshold = effective_window - AUTOCOMPACT_BUFFER_TOKENS

    # Allow percentage override for testing
    env_percent = os.environ.get("CLAUDE_AUTOCOMPACT_PCT_OVERRIDE")
    if env_percent:
        try:
            parsed = float(env_percent)
            if 0 < parsed <= 100:
                pct_threshold = int(effective_window * (parsed / 100))
                return min(pct_threshold, threshold)
        except ValueError:
            pass

    return threshold


# ---------------------------------------------------------------------------
# Token warning state
# ---------------------------------------------------------------------------

def calculate_token_warning_state(
    token_usage: int,
    model: str,
) -> Dict[str, Any]:
    """
    Calculate various token-usage thresholds and warning flags.
    Ported from calculateTokenWarningState().

    Returns a dict with:
        percent_left, is_above_warning_threshold, is_above_error_threshold,
        is_above_auto_compact_threshold, is_at_blocking_limit
    """
    auto_compact_threshold = get_auto_compact_threshold(model)
    threshold = (
        auto_compact_threshold
        if is_auto_compact_enabled()
        else get_effective_context_window_size(model)
    )

    percent_left = max(
        0,
        round(((threshold - token_usage) / threshold) * 100),
    )

    warning_threshold = threshold - WARNING_THRESHOLD_BUFFER_TOKENS
    error_threshold = threshold - ERROR_THRESHOLD_BUFFER_TOKENS

    is_above_warning_threshold = token_usage >= warning_threshold
    is_above_error_threshold = token_usage >= error_threshold
    is_above_auto_compact_threshold = (
        is_auto_compact_enabled() and token_usage >= auto_compact_threshold
    )

    actual_context_window = get_effective_context_window_size(model)
    default_blocking_limit = actual_context_window - MANUAL_COMPACT_BUFFER_TOKENS

    # Allow blocking-limit override for testing
    blocking_limit_override = os.environ.get("CLAUDE_CODE_BLOCKING_LIMIT_OVERRIDE")
    if blocking_limit_override:
        try:
            parsed_override = int(blocking_limit_override)
            if parsed_override > 0:
                blocking_limit = parsed_override
            else:
                blocking_limit = default_blocking_limit
        except ValueError:
            blocking_limit = default_blocking_limit
    else:
        blocking_limit = default_blocking_limit

    is_at_blocking_limit = token_usage >= blocking_limit

    return {
        "percent_left": percent_left,
        "is_above_warning_threshold": is_above_warning_threshold,
        "is_above_error_threshold": is_above_error_threshold,
        "is_above_auto_compact_threshold": is_above_auto_compact_threshold,
        "is_at_blocking_limit": is_at_blocking_limit,
    }


# ---------------------------------------------------------------------------
# Auto-compact enabled check
# ---------------------------------------------------------------------------

def is_auto_compact_enabled() -> bool:
    """
    Returns True when auto-compact is enabled (based on env vars and user config).
    Ported from isAutoCompactEnabled().
    """
    if is_env_truthy(os.environ.get("DISABLE_COMPACT")):
        return False
    if is_env_truthy(os.environ.get("DISABLE_AUTO_COMPACT")):
        return False
    user_config = get_global_config()
    return bool(getattr(user_config, "autoCompactEnabled", True))


# ---------------------------------------------------------------------------
# AutoCompactTrackingState
# ---------------------------------------------------------------------------

class AutoCompactTrackingState:
    """Tracking state for auto-compact across turns. Ported from AutoCompactTrackingState."""

    def __init__(
        self,
        compacted: bool = False,
        turn_counter: int = 0,
        turn_id: str = "",
        consecutive_failures: Optional[int] = None,
    ) -> None:
        self.compacted = compacted
        self.turn_counter = turn_counter
        self.turn_id = turn_id
        self.consecutive_failures = consecutive_failures

    def __repr__(self) -> str:
        return (
            f"AutoCompactTrackingState(compacted={self.compacted}, "
            f"turn_counter={self.turn_counter}, "
            f"consecutive_failures={self.consecutive_failures})"
        )


# ---------------------------------------------------------------------------
# shouldAutoCompact
# ---------------------------------------------------------------------------

async def should_auto_compact(
    messages: List[Dict[str, Any]],
    model: str,
    query_source: Optional[str] = None,
    snip_tokens_freed: int = 0,
) -> bool:
    """
    Determine whether the conversation is over the auto-compact threshold.
    Ported from shouldAutoCompact().
    """
    # Recursion guards: session_memory and compact are forked agents
    if query_source in ("session_memory", "compact"):
        return False

    # Context-collapse agent guard
    context_collapse_enabled = os.environ.get("FEATURE_CONTEXT_COLLAPSE", "").lower() in ("1", "true", "yes")
    if context_collapse_enabled and query_source == "marble_origami":
        return False

    if not is_auto_compact_enabled():
        return False

    # Reactive-only mode suppresses proactive autocompact
    reactive_compact_enabled = os.environ.get("FEATURE_REACTIVE_COMPACT", "").lower() in ("1", "true", "yes")
    if reactive_compact_enabled:
        if _get_feature_value("tengu_cobalt_raccoon", False):
            return False

    # Context-collapse mode: collapse owns context management — don't race it
    if context_collapse_enabled:
        try:
            from claude_code.services.context_collapse.index import is_context_collapse_enabled  # type: ignore
            if is_context_collapse_enabled():
                return False
        except ImportError:
            pass

    token_count = token_count_with_estimation(messages) - snip_tokens_freed
    threshold = get_auto_compact_threshold(model)
    effective_window = get_effective_context_window_size(model)

    log_for_debugging(
        f"autocompact: tokens={token_count} threshold={threshold} "
        f"effectiveWindow={effective_window}"
        + (f" snipFreed={snip_tokens_freed}" if snip_tokens_freed > 0 else "")
    )

    warning_state = calculate_token_warning_state(token_count, model)
    return bool(warning_state["is_above_auto_compact_threshold"])


# ---------------------------------------------------------------------------
# autoCompactIfNeeded
# ---------------------------------------------------------------------------

async def auto_compact_if_needed(
    messages: List[Dict[str, Any]],
    tool_use_context: Any,
    cache_safe_params: Any,
    query_source: Optional[str] = None,
    tracking: Optional[AutoCompactTrackingState] = None,
    snip_tokens_freed: int = 0,
) -> Dict[str, Any]:
    """
    Run auto-compact if the token threshold is exceeded.

    Returns a dict:
        was_compacted: bool
        compaction_result: Optional[CompactionResult]  — present when was_compacted=True
        consecutive_failures: Optional[int]            — updated failure count
    Ported from autoCompactIfNeeded().
    """
    if is_env_truthy(os.environ.get("DISABLE_COMPACT")):
        return {"was_compacted": False}

    # Circuit breaker: stop after N consecutive failures
    if (
        tracking is not None
        and tracking.consecutive_failures is not None
        and tracking.consecutive_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES
    ):
        return {"was_compacted": False}

    model: str = ""
    opts = getattr(tool_use_context, "options", None)
    if opts is not None:
        model = getattr(opts, "main_loop_model", "") or getattr(opts, "mainLoopModel", "") or ""

    should_compact = await should_auto_compact(
        messages, model, query_source, snip_tokens_freed
    )

    if not should_compact:
        return {"was_compacted": False}

    # Build RecompactionInfo
    try:
        recompaction_info = RecompactionInfo(
            is_recompaction_in_chain=(tracking.compacted if tracking else False),
            turns_since_previous_compact=(tracking.turn_counter if tracking else -1),
            previous_compact_turn_id=(tracking.turn_id if tracking else None),
            auto_compact_threshold=get_auto_compact_threshold(model),
            query_source=query_source,
        )
    except Exception:
        recompaction_info = {  # type: ignore[assignment]
            "is_recompaction_in_chain": tracking.compacted if tracking else False,
            "turns_since_previous_compact": tracking.turn_counter if tracking else -1,
            "auto_compact_threshold": get_auto_compact_threshold(model),
            "query_source": query_source,
        }

    agent_id = getattr(tool_use_context, "agent_id", None)

    # EXPERIMENT: Try session-memory compaction first
    try:
        session_memory_result = await try_session_memory_compaction(
            messages,
            agent_id,
            _get_auto_compact_threshold_value(recompaction_info),
        )
    except Exception:
        session_memory_result = None

    if session_memory_result is not None:
        set_last_summarized_message_id(None)
        run_post_compact_cleanup(query_source)

        prompt_cache_break = os.environ.get("FEATURE_PROMPT_CACHE_BREAK_DETECTION", "").lower() in ("1", "true", "yes")
        if prompt_cache_break:
            notify_compaction(query_source or "compact", agent_id)

        mark_post_compaction()

        return {
            "was_compacted": True,
            "compaction_result": session_memory_result,
        }

    # Fall back to full compact_conversation
    try:
        compaction_result = await compact_conversation(
            messages=messages,
            context=tool_use_context,
            cache_safe_params=cache_safe_params,
            suppress_follow_up_questions=True,   # suppress user questions for autocompact
            custom_instructions=None,
            is_auto_compact=True,
            recompaction_info=recompaction_info,
        )

        set_last_summarized_message_id(None)
        run_post_compact_cleanup(query_source)

        return {
            "was_compacted": True,
            "compaction_result": compaction_result,
            "consecutive_failures": 0,
        }
    except Exception as error:
        if not has_exact_error_message(error, ERROR_MESSAGE_USER_ABORT):
            log_error(error)

        prev_failures = (tracking.consecutive_failures or 0) if tracking else 0
        next_failures = prev_failures + 1

        if next_failures >= MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES:
            log_for_debugging(
                f"autocompact: circuit breaker tripped after {next_failures} "
                "consecutive failures — skipping future attempts this session",
                level="warn",
            )

        return {"was_compacted": False, "consecutive_failures": next_failures}


def _get_auto_compact_threshold_value(recompaction_info: Any) -> Optional[int]:
    """Extract auto_compact_threshold from a RecompactionInfo (dataclass or dict)."""
    if isinstance(recompaction_info, dict):
        return recompaction_info.get("auto_compact_threshold")
    return getattr(recompaction_info, "auto_compact_threshold", None)

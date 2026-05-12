"""
MicroCompact service.
Ported from services/compact/microCompact.ts

Provides token-saving micro-compaction of tool results:
 - Time-based: clears old tool results when the cache is cold (gap > threshold).
 - Cached MC: uses cache-edit API to delete tool results without breaking the cache.
"""
from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional, Set, Tuple

# ---------------------------------------------------------------------------
# Tool names — import with graceful fallback
# ---------------------------------------------------------------------------
try:
    from claude_code.constants.tools import (
        FILE_EDIT_TOOL_NAME,
        FILE_READ_TOOL_NAME,
        FILE_WRITE_TOOL_NAME,
        GLOB_TOOL_NAME,
        GREP_TOOL_NAME,
    )
except ImportError:
    FILE_EDIT_TOOL_NAME = "Edit"
    FILE_READ_TOOL_NAME = "Read"
    FILE_WRITE_TOOL_NAME = "Write"
    GLOB_TOOL_NAME = "Glob"
    GREP_TOOL_NAME = "Grep"

try:
    from claude_code.tools.web_fetch_tool.prompt import WEB_FETCH_TOOL_NAME  # type: ignore
except ImportError:
    WEB_FETCH_TOOL_NAME = "WebFetch"

try:
    from claude_code.tools.web_search_tool.prompt import WEB_SEARCH_TOOL_NAME  # type: ignore
except ImportError:
    WEB_SEARCH_TOOL_NAME = "WebSearch"

try:
    from claude_code.utils.shell.shell_tool_utils import SHELL_TOOL_NAMES  # type: ignore
except ImportError:
    SHELL_TOOL_NAMES: List[str] = ["Bash"]

# ---------------------------------------------------------------------------
# Compact warning state
# ---------------------------------------------------------------------------
try:
    from claude_code.services.compact.compact_warning_state import (
        set_compact_warning_shown as _set_warning,
        get_compact_warning_shown as _get_warning,
    )

    def suppress_compact_warning() -> None:
        _set_warning(True)

    def clear_compact_warning_suppression() -> None:
        _set_warning(False)
except ImportError:
    _warning_suppressed = False

    def suppress_compact_warning() -> None:  # type: ignore[misc]
        global _warning_suppressed
        _warning_suppressed = True

    def clear_compact_warning_suppression() -> None:  # type: ignore[misc]
        global _warning_suppressed
        _warning_suppressed = False

# ---------------------------------------------------------------------------
# Logging / analytics
# ---------------------------------------------------------------------------
try:
    from claude_code.utils.debug import log_for_debugging  # type: ignore
except ImportError:
    def log_for_debugging(msg: str, **kwargs: Any) -> None:  # type: ignore[misc]
        pass

try:
    from claude_code.services.analytics.index import log_event  # type: ignore
except ImportError:
    def log_event(name: str, props: Any = None) -> None:  # type: ignore[misc]
        pass

# ---------------------------------------------------------------------------
# Time-based MC config
# ---------------------------------------------------------------------------
try:
    from claude_code.services.compact.time_based_m_c_config import (
        TimeBasedMCConfig,
        get_time_based_mc_config,
    )
except ImportError:
    from dataclasses import dataclass

    @dataclass  # type: ignore[misc]
    class TimeBasedMCConfig:  # type: ignore[no-redef]
        enabled: bool
        gap_threshold_minutes: int
        keep_recent: int

    def get_time_based_mc_config() -> TimeBasedMCConfig:  # type: ignore[misc]
        return TimeBasedMCConfig(enabled=False, gap_threshold_minutes=60, keep_recent=5)

# ---------------------------------------------------------------------------
# Token estimation
# ---------------------------------------------------------------------------
try:
    from claude_code.services.token_estimation import estimate_tokens_from_string as _rough_tokens  # type: ignore
except ImportError:
    def _rough_tokens(text: str) -> int:  # type: ignore[misc]
        return max(1, len(text) // 4)


def _rough_token_count_estimation(text: str) -> int:
    return _rough_tokens(text)

# ---------------------------------------------------------------------------
# prompt cache break detection
# ---------------------------------------------------------------------------
try:
    from claude_code.services.api.prompt_cache_break_detection import notify_cache_deletion  # type: ignore
except ImportError:
    def notify_cache_deletion(query_source: str) -> None:  # type: ignore[misc]
        pass

# ---------------------------------------------------------------------------
# Cached microcompact module — lazy-loaded, ant-only (gated by feature flag)
# ---------------------------------------------------------------------------
_cached_mc_module: Any = None
_cached_mc_state: Any = None
_pending_cache_edits: Any = None


async def _get_cached_mc_module() -> Any:
    global _cached_mc_module
    if _cached_mc_module is None:
        try:
            from claude_code.services.compact import cached_microcompact as _mod  # type: ignore
            _cached_mc_module = _mod
        except ImportError:
            pass
    return _cached_mc_module


def _ensure_cached_mc_state() -> Any:
    global _cached_mc_state, _cached_mc_module
    if _cached_mc_state is None and _cached_mc_module is not None:
        _cached_mc_state = _cached_mc_module.create_cached_mc_state()
    if _cached_mc_state is None:
        raise RuntimeError(
            "cachedMCState not initialized — _get_cached_mc_module() must be called first"
        )
    return _cached_mc_state


def consume_pending_cache_edits() -> Any:
    """Return and clear the pending cache edits block (caller must pin them)."""
    global _pending_cache_edits
    edits = _pending_cache_edits
    _pending_cache_edits = None
    return edits


def get_pinned_cache_edits() -> List[Any]:
    """Return all previously-pinned cache edits (must be re-sent for cache hits)."""
    if _cached_mc_state is None:
        return []
    return getattr(_cached_mc_state, "pinned_edits", [])


def pin_cache_edits(user_message_index: int, block: Any) -> None:
    """Pin a new cache_edits block to a specific user message position."""
    if _cached_mc_state is not None:
        _cached_mc_state.pinned_edits.append({"userMessageIndex": user_message_index, "block": block})


def mark_tools_sent_to_api_state() -> None:
    """Mark all registered tools as sent to the API (call after successful API response)."""
    if _cached_mc_state is not None and _cached_mc_module is not None:
        _cached_mc_module.mark_tools_sent_to_api(_cached_mc_state)


def reset_microcompact_state() -> None:
    """Reset cached MC state (called after time-based compaction invalidates cache)."""
    global _pending_cache_edits
    if _cached_mc_state is not None and _cached_mc_module is not None:
        _cached_mc_module.reset_cached_mc_state(_cached_mc_state)
    _pending_cache_edits = None


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIME_BASED_MC_CLEARED_MESSAGE = "[Old tool result content cleared]"
IMAGE_MAX_TOKEN_SIZE = 2000

COMPACTABLE_TOOLS: Set[str] = {
    FILE_READ_TOOL_NAME,
    *SHELL_TOOL_NAMES,
    GREP_TOOL_NAME,
    GLOB_TOOL_NAME,
    WEB_SEARCH_TOOL_NAME,
    WEB_FETCH_TOOL_NAME,
    FILE_EDIT_TOOL_NAME,
    FILE_WRITE_TOOL_NAME,
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _calculate_tool_result_tokens(block: Dict[str, Any]) -> int:
    """Estimate tokens in a tool_result block."""
    content = block.get("content")
    if not content:
        return 0
    if isinstance(content, str):
        return _rough_token_count_estimation(content)
    # list of text/image/document blocks
    total = 0
    for item in content:
        itype = item.get("type", "")
        if itype == "text":
            total += _rough_token_count_estimation(item.get("text", ""))
        elif itype in ("image", "document"):
            total += IMAGE_MAX_TOKEN_SIZE
    return total


def _json_stringify(obj: Any) -> str:
    """Poor-man JSON stringify for token estimation."""
    try:
        import json
        return json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
    except Exception:
        return str(obj)


def estimate_message_tokens(messages: List[Dict[str, Any]]) -> int:
    """
    Estimate token count for messages by extracting text content.
    Pads estimate by 4/3 to be conservative.
    Ported from estimateMessageTokens().
    """
    total = 0

    for message in messages:
        msg_type = message.get("type")
        if msg_type not in ("user", "assistant"):
            continue

        content = message.get("message", {}).get("content")
        if not isinstance(content, list):
            continue

        for block in content:
            btype = block.get("type", "")
            if btype == "text":
                total += _rough_token_count_estimation(block.get("text", ""))
            elif btype == "tool_result":
                total += _calculate_tool_result_tokens(block)
            elif btype in ("image", "document"):
                total += IMAGE_MAX_TOKEN_SIZE
            elif btype == "thinking":
                total += _rough_token_count_estimation(block.get("thinking", ""))
            elif btype == "redacted_thinking":
                total += _rough_token_count_estimation(block.get("data", ""))
            elif btype == "tool_use":
                total += _rough_token_count_estimation(
                    block.get("name", "") + _json_stringify(block.get("input") or {})
                )
            else:
                total += _rough_token_count_estimation(_json_stringify(block))

    # Pad by 4/3 to be conservative
    return math.ceil(total * (4 / 3))


def _collect_compactable_tool_ids(messages: List[Dict[str, Any]]) -> List[str]:
    """Walk messages and collect tool_use IDs whose tool name is in COMPACTABLE_TOOLS."""
    ids: List[str] = []
    for message in messages:
        if message.get("type") != "assistant":
            continue
        content = message.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if block.get("type") == "tool_use" and block.get("name") in COMPACTABLE_TOOLS:
                ids.append(block["id"])
    return ids


def _is_main_thread_source(query_source: Optional[str]) -> bool:
    """True when the query source is the main REPL thread (prefix match)."""
    return query_source is None or query_source.startswith("repl_main_thread")


# ---------------------------------------------------------------------------
# PendingCacheEdits / MicrocompactResult types
# ---------------------------------------------------------------------------

class PendingCacheEdits:
    """Info about cache-edits queued for the next API request."""
    def __init__(
        self,
        trigger: str,
        deleted_tool_ids: List[str],
        baseline_cache_deleted_tokens: int,
    ) -> None:
        self.trigger = trigger
        self.deleted_tool_ids = deleted_tool_ids
        self.baseline_cache_deleted_tokens = baseline_cache_deleted_tokens

    def __repr__(self) -> str:
        return (
            f"PendingCacheEdits(trigger={self.trigger!r}, "
            f"deleted={len(self.deleted_tool_ids)}, "
            f"baseline={self.baseline_cache_deleted_tokens})"
        )


class MicrocompactResult:
    """Result returned by microcompactMessages."""
    def __init__(
        self,
        messages: List[Dict[str, Any]],
        compaction_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.messages = messages
        self.compaction_info = compaction_info  # may contain pending_cache_edits


# ---------------------------------------------------------------------------
# Time-based trigger evaluation
# ---------------------------------------------------------------------------

def evaluate_time_based_trigger(
    messages: List[Dict[str, Any]],
    query_source: Optional[str],
) -> Optional[Dict[str, Any]]:
    """
    Check whether the time-based trigger should fire.
    Returns {'gap_minutes': float, 'config': TimeBasedMCConfig} when it does,
    or None when it doesn't.
    Ported from evaluateTimeBasedTrigger().
    """
    config = get_time_based_mc_config()
    # Require an explicit main-thread querySource (unlike cached-MC, which
    # treats undefined as main-thread for backward compat)
    if not config.enabled or not query_source or not _is_main_thread_source(query_source):
        return None

    # Find the last assistant message
    last_assistant: Optional[Dict[str, Any]] = None
    for m in reversed(messages):
        if m.get("type") == "assistant":
            last_assistant = m
            break

    if last_assistant is None:
        return None

    import time as _time
    from datetime import datetime, timezone

    timestamp_str: Optional[str] = last_assistant.get("timestamp")
    if not timestamp_str:
        return None

    try:
        # Parse ISO-8601 timestamp
        ts = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        now_ms = _time.time() * 1000
        then_ms = ts.timestamp() * 1000
        gap_minutes = (now_ms - then_ms) / 60_000
    except Exception:
        return None

    if not math.isfinite(gap_minutes) or gap_minutes < config.gap_threshold_minutes:
        return None

    return {"gap_minutes": gap_minutes, "config": config}


def _maybe_time_based_microcompact(
    messages: List[Dict[str, Any]],
    query_source: Optional[str],
) -> Optional[MicrocompactResult]:
    """
    If the time-based trigger fires, content-clear old tool results and return
    a MicrocompactResult.  Returns None if the trigger doesn't fire.
    Ported from maybeTimeBasedMicrocompact().
    """
    trigger_info = evaluate_time_based_trigger(messages, query_source)
    if trigger_info is None:
        return None

    gap_minutes: float = trigger_info["gap_minutes"]
    config: TimeBasedMCConfig = trigger_info["config"]

    compactable_ids = _collect_compactable_tool_ids(messages)
    keep_recent = max(1, config.keep_recent)
    keep_set: Set[str] = set(compactable_ids[-keep_recent:])
    clear_set: Set[str] = {i for i in compactable_ids if i not in keep_set}

    if not clear_set:
        return None

    tokens_saved = 0

    def _map_message(message: Dict[str, Any]) -> Dict[str, Any]:
        nonlocal tokens_saved
        if message.get("type") != "user":
            return message
        content = message.get("message", {}).get("content")
        if not isinstance(content, list):
            return message

        touched = False
        new_content = []
        for block in content:
            if (
                block.get("type") == "tool_result"
                and block.get("tool_use_id") in clear_set
                and block.get("content") != TIME_BASED_MC_CLEARED_MESSAGE
            ):
                tokens_saved += _calculate_tool_result_tokens(block)
                touched = True
                new_content.append({**block, "content": TIME_BASED_MC_CLEARED_MESSAGE})
            else:
                new_content.append(block)

        if not touched:
            return message
        return {
            **message,
            "message": {**message["message"], "content": new_content},
        }

    result_messages = [_map_message(m) for m in messages]

    if tokens_saved == 0:
        return None

    log_event("tengu_time_based_microcompact", {
        "gapMinutes": round(gap_minutes),
        "gapThresholdMinutes": config.gap_threshold_minutes,
        "toolsCleared": len(clear_set),
        "toolsKept": len(keep_set),
        "keepRecent": config.keep_recent,
        "tokensSaved": tokens_saved,
    })

    log_for_debugging(
        f"[TIME-BASED MC] gap {round(gap_minutes)}min > "
        f"{config.gap_threshold_minutes}min, cleared {len(clear_set)} tool results "
        f"(~{tokens_saved} tokens), kept last {len(keep_set)}"
    )

    suppress_compact_warning()
    reset_microcompact_state()

    # Feature flag: CACHED_MICROCOMPACT → os.environ.get
    prompt_cache_break = os.environ.get("FEATURE_PROMPT_CACHE_BREAK_DETECTION", "").lower() in ("1", "true", "yes")
    if prompt_cache_break and query_source:
        notify_cache_deletion(query_source)

    return MicrocompactResult(messages=result_messages)


# ---------------------------------------------------------------------------
# Cached microcompact path
# ---------------------------------------------------------------------------

async def _cached_microcompact_path(
    messages: List[Dict[str, Any]],
    query_source: Optional[str],
) -> MicrocompactResult:
    """
    Cached microcompact path — uses cache-editing API to remove tool results
    without invalidating the cached prefix.
    Ported from cachedMicrocompactPath().
    """
    global _pending_cache_edits

    mod = await _get_cached_mc_module()
    if mod is None:
        return MicrocompactResult(messages=messages)

    state = _ensure_cached_mc_state()
    config = mod.get_cached_mc_config()

    compactable_tool_ids: Set[str] = set(_collect_compactable_tool_ids(messages))

    # Register tool results grouped by user message
    for message in messages:
        if message.get("type") != "user":
            continue
        content = message.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        group_ids: List[str] = []
        for block in content:
            if (
                block.get("type") == "tool_result"
                and block.get("tool_use_id") in compactable_tool_ids
                and block.get("tool_use_id") not in state.registered_tools
            ):
                mod.register_tool_result(state, block["tool_use_id"])
                group_ids.append(block["tool_use_id"])
        mod.register_tool_message(state, group_ids)

    tools_to_delete: List[str] = mod.get_tool_results_to_delete(state)

    if tools_to_delete:
        cache_edits = mod.create_cache_edits_block(state, tools_to_delete)
        if cache_edits:
            _pending_cache_edits = cache_edits

        log_for_debugging(
            f"Cached MC deleting {len(tools_to_delete)} tool(s): "
            f"{', '.join(tools_to_delete)}"
        )

        log_event("tengu_cached_microcompact", {
            "toolsDeleted": len(tools_to_delete),
            "deletedToolIds": ",".join(tools_to_delete),
            "activeToolCount": len(state.tool_order) - len(state.deleted_refs),
            "triggerType": "auto",
            "threshold": config.trigger_threshold,
            "keepRecent": config.keep_recent,
        })

        suppress_compact_warning()

        prompt_cache_break = os.environ.get("FEATURE_PROMPT_CACHE_BREAK_DETECTION", "").lower() in ("1", "true", "yes")
        if prompt_cache_break:
            notify_cache_deletion(query_source or "repl_main_thread")

        # Find baseline cumulative cache_deleted_input_tokens
        last_asst: Optional[Dict[str, Any]] = None
        for m in reversed(messages):
            if m.get("type") == "assistant":
                last_asst = m
                break

        baseline = 0
        if last_asst is not None:
            usage = last_asst.get("message", {}).get("usage") or {}
            if isinstance(usage, dict):
                baseline = int(usage.get("cache_deleted_input_tokens", 0))

        return MicrocompactResult(
            messages=messages,
            compaction_info={
                "pending_cache_edits": PendingCacheEdits(
                    trigger="auto",
                    deleted_tool_ids=tools_to_delete,
                    baseline_cache_deleted_tokens=baseline,
                )
            },
        )

    # No compaction needed
    return MicrocompactResult(messages=messages)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def microcompact_messages(
    messages: List[Dict[str, Any]],
    tool_use_context: Any = None,
    query_source: Optional[str] = None,
) -> MicrocompactResult:
    """
    Walk messages and apply micro-compaction:
      1. Time-based: content-clear old tool results if the cache is cold.
      2. Cached MC: queue cache-edits if feature-flagged and supported.
      3. Otherwise: return messages unchanged.

    Ported from microcompactMessages().
    """
    clear_compact_warning_suppression()

    # Time-based trigger runs first and short-circuits
    time_based = _maybe_time_based_microcompact(messages, query_source)
    if time_based is not None:
        return time_based

    # Cached MC (ant-only, gated by FEATURE_CACHED_MICROCOMPACT env var)
    cached_mc_enabled = os.environ.get("FEATURE_CACHED_MICROCOMPACT", "").lower() in ("1", "true", "yes")
    if cached_mc_enabled:
        mod = await _get_cached_mc_module()
        if mod is not None:
            # Determine model
            model = ""
            if tool_use_context is not None:
                opts = getattr(tool_use_context, "options", None)
                if opts is not None:
                    model = getattr(opts, "main_loop_model", "") or ""
            if not model:
                try:
                    from claude_code.utils.model.model import get_main_loop_model  # type: ignore
                    model = get_main_loop_model()
                except ImportError:
                    pass

            if (
                mod.is_cached_microcompact_enabled()
                and mod.is_model_supported_for_cache_editing(model)
                and _is_main_thread_source(query_source)
            ):
                return await _cached_microcompact_path(messages, query_source)

    # No compaction — return messages unchanged
    return MicrocompactResult(messages=messages)

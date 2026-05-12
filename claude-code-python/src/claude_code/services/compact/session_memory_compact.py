"""
Session memory compaction service.
Ported from services/compact/sessionMemoryCompact.ts

Provides an alternative compaction path that uses session memory (notes file)
as the summary instead of calling the compaction API. Falls back to None when
session memory is not available or does not meet quality checks.
"""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Set

# ---------------------------------------------------------------------------
# Optional imports with graceful fallback
# ---------------------------------------------------------------------------

try:
    from claude_code.utils.debug import log_for_debugging  # type: ignore
except ImportError:
    def log_for_debugging(msg: str, **kwargs: Any) -> None:  # type: ignore[misc]
        pass

try:
    from claude_code.utils.errors import error_message as _error_message  # type: ignore
except ImportError:
    def _error_message(exc: Any) -> str:  # type: ignore[misc]
        return str(exc)

try:
    from claude_code.utils.messages import (  # type: ignore
        create_compact_boundary_message,
        create_user_message,
        is_compact_boundary_message,
    )
except ImportError:
    def create_compact_boundary_message(trigger: str, pre_tokens: int, last_uuid: Any = None) -> Dict[str, Any]:  # type: ignore[misc]
        return {"type": "system", "subtype": "compact_boundary", "compactMetadata": {"trigger": trigger, "preTokens": pre_tokens}}

    def create_user_message(*, content: Any, **kwargs: Any) -> Dict[str, Any]:  # type: ignore[misc]
        return {"type": "user", "role": "user", "content": content}

    def is_compact_boundary_message(message: Any) -> bool:  # type: ignore[misc]
        if isinstance(message, dict):
            return message.get("type") == "system" and message.get("subtype") == "compact_boundary"
        return getattr(message, "type", None) == "system" and getattr(message, "subtype", None) == "compact_boundary"

try:
    from claude_code.utils.model_utils import get_main_loop_model  # type: ignore
except ImportError:
    try:
        from claude_code.utils.model.model import get_main_loop_model  # type: ignore
    except ImportError:
        def get_main_loop_model() -> str:  # type: ignore[misc]
            return os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-20241022")

try:
    from claude_code.utils.session_storage import get_transcript_path  # type: ignore
except ImportError:
    def get_transcript_path() -> str:  # type: ignore[misc]
        return os.path.expanduser("~/.claude/projects/default/session.jsonl")

try:
    from claude_code.utils.session_start import process_session_start_hooks  # type: ignore
except ImportError:
    async def process_session_start_hooks(trigger: str, options: Any = None) -> List[Any]:  # type: ignore[misc]
        return []

try:
    from claude_code.services.analytics.growthbook import (  # type: ignore
        get_dynamic_config_blocks_on_init as _get_dynamic_config,
        get_feature_value_cached_may_be_stale as _get_feature_value,
    )
except ImportError:
    async def _get_dynamic_config(key: str, default: Any) -> Any:  # type: ignore[misc]
        return default

    def _get_feature_value(key: str, default: Any) -> Any:  # type: ignore[misc]
        return default

try:
    from claude_code.services.analytics.index import log_event  # type: ignore
except ImportError:
    try:
        from claude_code.services.analytics import log_event  # type: ignore
    except ImportError:
        def log_event(name: str, data: Any = None) -> None:  # type: ignore[misc]
            pass

try:
    from claude_code.services.session_memory.prompts import (  # type: ignore
        is_session_memory_empty,
        truncate_session_memory_for_compact,
    )
except ImportError:
    async def is_session_memory_empty(content: str) -> bool:  # type: ignore[misc]
        return not content or not content.strip()

    def truncate_session_memory_for_compact(content: str) -> Dict[str, Any]:  # type: ignore[misc]
        return {"truncatedContent": content, "wasTruncated": False}

try:
    from claude_code.services.session_memory.session_memory_utils import (  # type: ignore
        get_last_summarized_message_id,
        get_session_memory_content,
        wait_for_session_memory_extraction,
    )
except ImportError:
    def get_last_summarized_message_id() -> Optional[str]:  # type: ignore[misc]
        return None

    async def get_session_memory_content() -> Optional[str]:  # type: ignore[misc]
        return None

    async def wait_for_session_memory_extraction() -> None:  # type: ignore[misc]
        pass

try:
    from claude_code.services.compact.compact import (  # type: ignore
        CompactionResult,
        annotate_boundary_with_preserved_segment,
        build_post_compact_messages,
        create_plan_attachment_if_needed,
    )
except ImportError:
    from dataclasses import dataclass, field

    @dataclass
    class CompactionResult:  # type: ignore[no-redef]
        boundary_marker: Dict[str, Any]
        summary_messages: List[Dict[str, Any]]
        attachments: List[Dict[str, Any]]
        hook_results: List[Dict[str, Any]]
        messages_to_keep: Optional[List[Dict[str, Any]]] = None
        user_display_message: Optional[str] = None
        pre_compact_token_count: Optional[int] = None
        post_compact_token_count: Optional[int] = None
        true_post_compact_token_count: Optional[int] = None
        compaction_usage: Optional[Dict[str, Any]] = None

    def annotate_boundary_with_preserved_segment(  # type: ignore[misc]
        boundary: Dict[str, Any],
        anchor_uuid: str,
        messages_to_keep: Optional[List[Dict[str, Any]]],
    ) -> Dict[str, Any]:
        keep = messages_to_keep or []
        if not keep:
            return boundary
        updated = {
            **boundary,
            "compactMetadata": {
                **boundary.get("compactMetadata", {}),
                "preservedSegment": {
                    "headUuid": keep[0].get("uuid", ""),
                    "anchorUuid": anchor_uuid,
                    "tailUuid": keep[-1].get("uuid", ""),
                },
            },
        }
        return updated

    def build_post_compact_messages(result: "CompactionResult") -> List[Dict[str, Any]]:  # type: ignore[misc]
        return [
            result.boundary_marker,
            *result.summary_messages,
            *(result.messages_to_keep or []),
            *result.attachments,
            *result.hook_results,
        ]

    def create_plan_attachment_if_needed(agent_id: Any = None) -> Optional[Dict[str, Any]]:  # type: ignore[misc]
        return None

try:
    from claude_code.services.compact.micro_compact import estimate_message_tokens  # type: ignore
except ImportError:
    def estimate_message_tokens(messages: List[Dict[str, Any]]) -> int:  # type: ignore[misc]
        total = 0
        for m in messages:
            content = m.get("message", {}).get("content") or m.get("content") or ""
            total += max(1, len(str(content)) // 4)
        return total

try:
    from claude_code.services.compact.prompt import get_compact_user_summary_message  # type: ignore
except ImportError:
    def get_compact_user_summary_message(  # type: ignore[misc]
        summary: str,
        suppress_follow_up_questions: Optional[bool] = None,
        transcript_path: Optional[str] = None,
        recent_messages_preserved: Optional[bool] = None,
    ) -> str:
        return summary

try:
    from claude_code.services.tools.tool_execution import _extract_discovered_tool_names as _extract_tools  # type: ignore
except ImportError:
    def _extract_tools(messages: List[Any]) -> Set[str]:  # type: ignore[misc]
        return set()

try:
    from claude_code.services.api.claude import token_count_from_last_api_response  # type: ignore
except ImportError:
    def token_count_from_last_api_response(messages: List[Any]) -> Optional[int]:  # type: ignore[misc]
        return None

# ---------------------------------------------------------------------------
# Helper: get_session_memory_path
# ---------------------------------------------------------------------------

def _get_session_memory_path() -> str:
    """Get path to the session memory file."""
    try:
        from claude_code.utils.permissions.filesystem import get_session_memory_path  # type: ignore
        return get_session_memory_path()
    except ImportError:
        pass
    # fallback: look in ~/.claude
    base = os.environ.get("CLAUDE_CONFIG_HOME") or os.path.expanduser("~/.claude")
    session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
    return os.path.join(base, "projects", session_id, "session-memory.md")


# ---------------------------------------------------------------------------
# SessionMemoryCompactConfig
# ---------------------------------------------------------------------------

class SessionMemoryCompactConfig:
    """Configuration for session memory compaction thresholds."""

    def __init__(
        self,
        min_tokens: int,
        min_text_block_messages: int,
        max_tokens: int,
    ) -> None:
        self.min_tokens = min_tokens
        self.min_text_block_messages = min_text_block_messages
        self.max_tokens = max_tokens

    def copy(self) -> "SessionMemoryCompactConfig":
        return SessionMemoryCompactConfig(
            min_tokens=self.min_tokens,
            min_text_block_messages=self.min_text_block_messages,
            max_tokens=self.max_tokens,
        )


# Default configuration values (exported for use in tests)
DEFAULT_SM_COMPACT_CONFIG = SessionMemoryCompactConfig(
    min_tokens=10_000,
    min_text_block_messages=5,
    max_tokens=40_000,
)

# Current configuration (starts with defaults)
_sm_compact_config = DEFAULT_SM_COMPACT_CONFIG.copy()

# Track whether config has been initialized from remote
_config_initialized = False


def set_session_memory_compact_config(
    min_tokens: Optional[int] = None,
    min_text_block_messages: Optional[int] = None,
    max_tokens: Optional[int] = None,
) -> None:
    """Set the session memory compact configuration (partial update)."""
    global _sm_compact_config
    if min_tokens is not None:
        _sm_compact_config.min_tokens = min_tokens
    if min_text_block_messages is not None:
        _sm_compact_config.min_text_block_messages = min_text_block_messages
    if max_tokens is not None:
        _sm_compact_config.max_tokens = max_tokens


def get_session_memory_compact_config() -> SessionMemoryCompactConfig:
    """Get the current session memory compact configuration."""
    return _sm_compact_config.copy()


def reset_session_memory_compact_config() -> None:
    """Reset config state (useful for testing)."""
    global _sm_compact_config, _config_initialized
    _sm_compact_config = DEFAULT_SM_COMPACT_CONFIG.copy()
    _config_initialized = False


async def _init_session_memory_compact_config() -> None:
    """
    Initialize configuration from remote config (GrowthBook).
    Only fetches once per session — subsequent calls return immediately.
    """
    global _config_initialized
    if _config_initialized:
        return
    _config_initialized = True

    remote_config: Dict[str, Any] = await _get_dynamic_config("tengu_sm_compact_config", {})

    # Only use remote values if they are explicitly set (positive numbers)
    remote_min_tokens = remote_config.get("minTokens") or remote_config.get("min_tokens")
    remote_min_text = remote_config.get("minTextBlockMessages") or remote_config.get("min_text_block_messages")
    remote_max_tokens = remote_config.get("maxTokens") or remote_config.get("max_tokens")

    set_session_memory_compact_config(
        min_tokens=remote_min_tokens if remote_min_tokens and remote_min_tokens > 0 else None,
        min_text_block_messages=remote_min_text if remote_min_text and remote_min_text > 0 else None,
        max_tokens=remote_max_tokens if remote_max_tokens and remote_max_tokens > 0 else None,
    )


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def has_text_blocks(message: Any) -> bool:
    """
    Check if a message contains text blocks (text content for user/assistant interaction).
    Ported from hasTextBlocks().
    """
    msg_type = message.get("type") if isinstance(message, dict) else getattr(message, "type", None)

    if msg_type == "assistant":
        content = (
            message.get("message", {}).get("content")
            if isinstance(message, dict)
            else getattr(getattr(message, "message", None), "content", None)
        )
        if isinstance(content, list):
            return any(
                (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "text"
                for b in content
            )
        return False

    if msg_type == "user":
        content = (
            message.get("message", {}).get("content")
            if isinstance(message, dict)
            else getattr(getattr(message, "message", None), "content", None)
        )
        if isinstance(content, str):
            return len(content) > 0
        if isinstance(content, list):
            return any(
                (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "text"
                for b in content
            )
    return False


def _get_tool_result_ids(message: Any) -> List[str]:
    """
    Check if a message contains tool_result blocks and return their tool_use_ids.
    Ported from getToolResultIds().
    """
    msg_type = message.get("type") if isinstance(message, dict) else getattr(message, "type", None)
    if msg_type != "user":
        return []

    content = (
        message.get("message", {}).get("content")
        if isinstance(message, dict)
        else getattr(getattr(message, "message", None), "content", None)
    )
    if not isinstance(content, list):
        return []

    ids: List[str] = []
    for block in content:
        btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
        if btype == "tool_result":
            tool_use_id = (
                block.get("tool_use_id")
                if isinstance(block, dict)
                else getattr(block, "tool_use_id", None)
            )
            if tool_use_id:
                ids.append(tool_use_id)
    return ids


def _has_tool_use_with_ids(message: Any, tool_use_ids: Set[str]) -> bool:
    """
    Check if a message contains tool_use blocks with any of the given ids.
    Ported from hasToolUseWithIds().
    """
    msg_type = message.get("type") if isinstance(message, dict) else getattr(message, "type", None)
    if msg_type != "assistant":
        return False

    content = (
        message.get("message", {}).get("content")
        if isinstance(message, dict)
        else getattr(getattr(message, "message", None), "content", None)
    )
    if not isinstance(content, list):
        return False

    return any(
        (b.get("type") if isinstance(b, dict) else getattr(b, "type", None)) == "tool_use"
        and (b.get("id") if isinstance(b, dict) else getattr(b, "id", None)) in tool_use_ids
        for b in content
    )


def _get_message_id(message: Any) -> Optional[str]:
    """Extract message.id from a message object."""
    if isinstance(message, dict):
        return message.get("message", {}).get("id")
    msg = getattr(message, "message", None)
    return getattr(msg, "id", None) if msg else None


def _get_message_uuid(message: Any) -> Optional[str]:
    """Extract uuid from a message object."""
    if isinstance(message, dict):
        return message.get("uuid")
    return getattr(message, "uuid", None)


# ---------------------------------------------------------------------------
# adjustIndexToPreserveAPIInvariants
# ---------------------------------------------------------------------------

def adjust_index_to_preserve_api_invariants(
    messages: List[Any],
    start_index: int,
) -> int:
    """
    Adjust the start index to ensure we don't split tool_use/tool_result pairs
    or thinking blocks that share the same message.id with kept assistant messages.

    Handles two scenarios:
    1. Tool pair: if kept messages have tool_result blocks, find the preceding
       assistant messages with matching tool_use blocks.
    2. Thinking block: if kept assistant messages share a message.id with a
       preceding assistant message (containing thinking blocks), include that too.

    Ported from adjustIndexToPreserveAPIInvariants().
    """
    if start_index <= 0 or start_index >= len(messages):
        return start_index

    adjusted_index = start_index

    # Step 1: Handle tool_use/tool_result pairs
    # Collect tool_result IDs from ALL messages in the kept range
    all_tool_result_ids: List[str] = []
    for i in range(start_index, len(messages)):
        all_tool_result_ids.extend(_get_tool_result_ids(messages[i]))

    if all_tool_result_ids:
        # Collect tool_use IDs already in the kept range
        tool_use_ids_in_kept_range: Set[str] = set()
        for i in range(adjusted_index, len(messages)):
            msg = messages[i]
            msg_type = msg.get("type") if isinstance(msg, dict) else getattr(msg, "type", None)
            if msg_type == "assistant":
                content = (
                    msg.get("message", {}).get("content")
                    if isinstance(msg, dict)
                    else getattr(getattr(msg, "message", None), "content", None)
                )
                if isinstance(content, list):
                    for block in content:
                        btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                        if btype == "tool_use":
                            bid = block.get("id") if isinstance(block, dict) else getattr(block, "id", None)
                            if bid:
                                tool_use_ids_in_kept_range.add(bid)

        # Only look for tool_uses NOT already in the kept range
        needed_tool_use_ids: Set[str] = {
            tid for tid in all_tool_result_ids if tid not in tool_use_ids_in_kept_range
        }

        # Find the assistant message(s) with matching tool_use blocks
        i = adjusted_index - 1
        while i >= 0 and needed_tool_use_ids:
            message = messages[i]
            if _has_tool_use_with_ids(message, needed_tool_use_ids):
                adjusted_index = i
                # Remove found tool_use_ids from the set
                msg_type = message.get("type") if isinstance(message, dict) else getattr(message, "type", None)
                if msg_type == "assistant":
                    content = (
                        message.get("message", {}).get("content")
                        if isinstance(message, dict)
                        else getattr(getattr(message, "message", None), "content", None)
                    )
                    if isinstance(content, list):
                        for block in content:
                            btype = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                            if btype == "tool_use":
                                bid = block.get("id") if isinstance(block, dict) else getattr(block, "id", None)
                                if bid and bid in needed_tool_use_ids:
                                    needed_tool_use_ids.discard(bid)
            i -= 1

    # Step 2: Handle thinking blocks that share message.id with kept assistant messages
    # Collect all message.ids from assistant messages in the kept range
    message_ids_in_kept_range: Set[str] = set()
    for i in range(adjusted_index, len(messages)):
        msg = messages[i]
        msg_type = msg.get("type") if isinstance(msg, dict) else getattr(msg, "type", None)
        if msg_type == "assistant":
            mid = _get_message_id(msg)
            if mid:
                message_ids_in_kept_range.add(mid)

    # Look backwards for assistant messages with the same message.id not in kept range
    for i in range(adjusted_index - 1, -1, -1):
        message = messages[i]
        msg_type = message.get("type") if isinstance(message, dict) else getattr(message, "type", None)
        if msg_type == "assistant":
            mid = _get_message_id(message)
            if mid and mid in message_ids_in_kept_range:
                adjusted_index = i

    return adjusted_index


# ---------------------------------------------------------------------------
# calculateMessagesToKeepIndex
# ---------------------------------------------------------------------------

def calculate_messages_to_keep_index(
    messages: List[Any],
    last_summarized_index: int,
) -> int:
    """
    Calculate the starting index for messages to keep after compaction.

    Starts from lastSummarizedIndex, then expands backwards to meet minimums:
    - At least config.minTokens tokens
    - At least config.minTextBlockMessages messages with text blocks

    Stops expanding if config.maxTokens is reached.
    Also ensures tool_use/tool_result pairs are not split.

    Ported from calculateMessagesToKeepIndex().
    """
    if not messages:
        return 0

    config = get_session_memory_compact_config()

    # Start from the message after lastSummarizedIndex.
    # If lastSummarizedIndex is -1 (not found) or messages.length, no messages kept initially.
    if last_summarized_index >= 0:
        start_index = last_summarized_index + 1
    else:
        start_index = len(messages)

    # Calculate current tokens and text-block message count from startIndex to end
    total_tokens = 0
    text_block_message_count = 0
    for i in range(start_index, len(messages)):
        msg = messages[i]
        total_tokens += estimate_message_tokens([msg])
        if has_text_blocks(msg):
            text_block_message_count += 1

    # Check if we already hit the max cap
    if total_tokens >= config.max_tokens:
        return adjust_index_to_preserve_api_invariants(messages, start_index)

    # Check if we already meet both minimums
    if total_tokens >= config.min_tokens and text_block_message_count >= config.min_text_block_messages:
        return adjust_index_to_preserve_api_invariants(messages, start_index)

    # Determine the floor: the position just after the last compact boundary.
    # Do not expand past it — that's a disk discontinuity in the preserved-segment chain.
    floor = 0
    for idx in range(len(messages) - 1, -1, -1):
        if is_compact_boundary_message(messages[idx]):
            floor = idx + 1
            break

    # Expand backwards until we meet both minimums or hit max cap
    for i in range(start_index - 1, floor - 1, -1):
        msg = messages[i]
        msg_tokens = estimate_message_tokens([msg])
        total_tokens += msg_tokens
        if has_text_blocks(msg):
            text_block_message_count += 1
        start_index = i

        # Stop if we hit the max cap
        if total_tokens >= config.max_tokens:
            break

        # Stop if we meet both minimums
        if total_tokens >= config.min_tokens and text_block_message_count >= config.min_text_block_messages:
            break

    return adjust_index_to_preserve_api_invariants(messages, start_index)


# ---------------------------------------------------------------------------
# shouldUseSessionMemoryCompaction
# ---------------------------------------------------------------------------

def should_use_session_memory_compaction() -> bool:
    """
    Check if we should use session memory for compaction.
    Uses cached gate values to avoid blocking on Statsig initialization.
    Ported from shouldUseSessionMemoryCompaction().
    """
    # Allow env var override for eval runs and testing
    enable_sm = os.environ.get("ENABLE_CLAUDE_CODE_SM_COMPACT", "")
    if enable_sm.lower() in ("1", "true", "yes"):
        return True

    disable_sm = os.environ.get("DISABLE_CLAUDE_CODE_SM_COMPACT", "")
    if disable_sm.lower() in ("1", "true", "yes"):
        return False

    session_memory_flag = _get_feature_value("tengu_session_memory", False)
    sm_compact_flag = _get_feature_value("tengu_sm_compact", False)
    should_use = bool(session_memory_flag) and bool(sm_compact_flag)

    # Log flag states for debugging (ant-only to avoid noise in external logs)
    if os.environ.get("USER_TYPE") == "ant":
        log_event("tengu_sm_compact_flag_check", {
            "tengu_session_memory": session_memory_flag,
            "tengu_sm_compact": sm_compact_flag,
            "should_use": should_use,
        })

    return should_use


# ---------------------------------------------------------------------------
# _createCompactionResultFromSessionMemory
# ---------------------------------------------------------------------------

def _create_compaction_result_from_session_memory(
    messages: List[Any],
    session_memory: str,
    messages_to_keep: List[Any],
    hook_results: List[Any],
    transcript_path: str,
    agent_id: Optional[str] = None,
) -> "CompactionResult":
    """
    Create a CompactionResult from session memory.
    Ported from createCompactionResultFromSessionMemory().
    """
    pre_compact_token_count = token_count_from_last_api_response(messages)

    last_uuid = _get_message_uuid(messages[-1]) if messages else None
    boundary_marker = create_compact_boundary_message(
        "auto",
        pre_compact_token_count or 0,
        last_uuid,
    )

    # Annotate boundary with discovered tools
    pre_compact_discovered: Set[str] = _extract_tools(messages)
    if pre_compact_discovered:
        # Update compactMetadata.preCompactDiscoveredTools
        if isinstance(boundary_marker, dict):
            meta = boundary_marker.get("compactMetadata") or boundary_marker.get("extra_data", {}).get("compactMetadata", {})
            if meta is not None:
                meta["preCompactDiscoveredTools"] = sorted(pre_compact_discovered)
        else:
            compact_meta = getattr(boundary_marker, "compactMetadata", None)
            if compact_meta is None:
                extra = getattr(boundary_marker, "extra_data", {}) or {}
                compact_meta = extra.get("compactMetadata")
            if compact_meta is not None:
                if isinstance(compact_meta, dict):
                    compact_meta["preCompactDiscoveredTools"] = sorted(pre_compact_discovered)

    # Truncate oversized sections to prevent session memory from consuming
    # the entire post-compact token budget
    truncate_result = truncate_session_memory_for_compact(session_memory)
    truncated_content: str = truncate_result["truncatedContent"]  # type: ignore[index]
    was_truncated: bool = truncate_result["wasTruncated"]  # type: ignore[index]

    summary_content = get_compact_user_summary_message(
        truncated_content,
        True,          # suppress_follow_up_questions
        transcript_path,
        True,          # recent_messages_preserved
    )

    if was_truncated:
        memory_path = _get_session_memory_path()
        summary_content += (
            f"\n\nSome session memory sections were truncated for length. "
            f"The full session memory can be viewed at: {memory_path}"
        )

    summary_messages = [
        create_user_message(
            content=summary_content,
            is_compact_summary=True,
            is_visible_in_transcript_only=True,
        )
    ]

    plan_attachment = create_plan_attachment_if_needed(agent_id)
    attachments = [plan_attachment] if plan_attachment else []

    # Annotate boundary with preserved segment info
    last_summary_uuid = _get_message_uuid(summary_messages[-1]) if summary_messages else ""
    annotated_boundary = annotate_boundary_with_preserved_segment(
        boundary_marker if isinstance(boundary_marker, dict) else _message_to_dict(boundary_marker),
        last_summary_uuid or "",
        [m if isinstance(m, dict) else _message_to_dict(m) for m in messages_to_keep],
    )

    post_compact_token_count = estimate_message_tokens(summary_messages)

    return CompactionResult(
        boundary_marker=annotated_boundary,
        summary_messages=[m if isinstance(m, dict) else _message_to_dict(m) for m in summary_messages],
        attachments=attachments,
        hook_results=[m if isinstance(m, dict) else _message_to_dict(m) for m in hook_results],
        messages_to_keep=[m if isinstance(m, dict) else _message_to_dict(m) for m in messages_to_keep],
        pre_compact_token_count=pre_compact_token_count,
        # SM-compact has no compact-API-call, so postCompactTokenCount and
        # truePostCompactTokenCount converge to the same value.
        post_compact_token_count=post_compact_token_count,
        true_post_compact_token_count=post_compact_token_count,
    )


def _message_to_dict(message: Any) -> Dict[str, Any]:
    """Convert a message object to dict if it isn't one already."""
    if isinstance(message, dict):
        return message
    # dataclass / namedtuple / object with __dict__
    if hasattr(message, "__dict__"):
        return {k: v for k, v in vars(message).items() if not k.startswith("_")}
    return {}


# ---------------------------------------------------------------------------
# trySessionMemoryCompaction
# ---------------------------------------------------------------------------

async def try_session_memory_compaction(
    messages: List[Any],
    agent_id: Optional[str] = None,
    auto_compact_threshold: Optional[int] = None,
) -> Optional["CompactionResult"]:
    """
    Try to use session memory for compaction instead of traditional compaction.
    Returns None if session memory compaction cannot be used.

    Handles two scenarios:
    1. Normal case: lastSummarizedMessageId is set, keep only messages after that ID
    2. Resumed session: lastSummarizedMessageId is not set but session memory has content,
       keep all messages but use session memory as the summary.

    Ported from trySessionMemoryCompaction().
    """
    if not should_use_session_memory_compaction():
        return None

    # Initialize config from remote (only fetches once)
    await _init_session_memory_compact_config()

    # Wait for any in-progress session memory extraction to complete (with timeout)
    await wait_for_session_memory_extraction()

    last_summarized_message_id = get_last_summarized_message_id()
    session_memory = await get_session_memory_content()

    # No session memory file exists at all
    if not session_memory:
        log_event("tengu_sm_compact_no_session_memory", {})
        return None

    # Session memory exists but matches the template (no actual content extracted)
    # Fall back to legacy compact behavior
    if await is_session_memory_empty(session_memory):
        log_event("tengu_sm_compact_empty_template", {})
        return None

    try:
        if last_summarized_message_id:
            # Normal case: we know exactly which messages have been summarized
            last_summarized_index = next(
                (i for i, msg in enumerate(messages)
                 if _get_message_uuid(msg) == last_summarized_message_id),
                -1,
            )

            if last_summarized_index == -1:
                # The summarized message ID doesn't exist in current messages.
                # Fall back to legacy compact — we can't determine the boundary.
                log_event("tengu_sm_compact_summarized_id_not_found", {})
                return None
        else:
            # Resumed session case: session memory has content but we don't know the boundary.
            # Set lastSummarizedIndex to last message so startIndex becomes messages.length.
            last_summarized_index = len(messages) - 1
            log_event("tengu_sm_compact_resumed_session", {})

        # Calculate the starting index for messages to keep
        start_index = calculate_messages_to_keep_index(messages, last_summarized_index)

        # Filter out old compact boundary messages from messagesToKeep.
        # After REPL pruning, old boundaries re-yielded from messagesToKeep would
        # trigger an unwanted second prune (isCompactBoundaryMessage returns true).
        messages_to_keep = [
            m for m in messages[start_index:]
            if not is_compact_boundary_message(m)
        ]

        # Run session start hooks to restore CLAUDE.md and other context
        hook_results = await process_session_start_hooks("compact", {
            "model": get_main_loop_model(),
        })

        # Get transcript path for the summary message
        transcript_path = get_transcript_path()

        compaction_result = _create_compaction_result_from_session_memory(
            messages,
            session_memory,
            messages_to_keep,
            hook_results,
            transcript_path,
            agent_id,
        )

        post_compact_messages = build_post_compact_messages(compaction_result)
        post_compact_token_count = estimate_message_tokens(post_compact_messages)

        # Only check threshold if one was provided (for autocompact)
        if (
            auto_compact_threshold is not None
            and post_compact_token_count >= auto_compact_threshold
        ):
            log_event("tengu_sm_compact_threshold_exceeded", {
                "postCompactTokenCount": post_compact_token_count,
                "autoCompactThreshold": auto_compact_threshold,
            })
            return None

        # Return result with updated token counts
        return CompactionResult(
            boundary_marker=compaction_result.boundary_marker,
            summary_messages=compaction_result.summary_messages,
            attachments=compaction_result.attachments,
            hook_results=compaction_result.hook_results,
            messages_to_keep=compaction_result.messages_to_keep,
            pre_compact_token_count=compaction_result.pre_compact_token_count,
            post_compact_token_count=post_compact_token_count,
            true_post_compact_token_count=post_compact_token_count,
        )

    except Exception as error:
        # Use log_event instead of log_error since errors here are expected
        # (e.g., file not found, path issues) and shouldn't go to error logs
        log_event("tengu_sm_compact_error", {})
        if os.environ.get("USER_TYPE") == "ant":
            log_for_debugging(
                f"Session memory compaction error: {_error_message(error)}"
            )
        return None

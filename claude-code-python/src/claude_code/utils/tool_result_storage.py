"""
Utility for persisting large tool results to disk instead of truncating them.

原始 TS: utils/toolResultStorage.ts (1040 行)

GrowthBook / analytics dependencies are stubbed out — no external feature-flag
service is required.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

# ---------------------------------------------------------------------------
# Constants (mirrors constants/toolLimits.ts)
# ---------------------------------------------------------------------------

#: Default maximum size in characters before persisting to disk.
DEFAULT_MAX_RESULT_SIZE_CHARS: int = 50_000

#: Maximum size for tool results in tokens.
MAX_TOOL_RESULT_TOKENS: int = 100_000

#: Bytes per token estimate.
BYTES_PER_TOKEN: int = 4

#: Maximum size for tool results in bytes (derived from token limit).
MAX_TOOL_RESULT_BYTES: int = MAX_TOOL_RESULT_TOKENS * BYTES_PER_TOKEN

#: Maximum aggregate size in characters for tool_result blocks in one user message.
MAX_TOOL_RESULTS_PER_MESSAGE_CHARS: int = 200_000

# ---------------------------------------------------------------------------
# Sub-directory / tag constants
# ---------------------------------------------------------------------------

TOOL_RESULTS_SUBDIR: str = "tool-results"
PERSISTED_OUTPUT_TAG: str = "<persisted-output>"
PERSISTED_OUTPUT_CLOSING_TAG: str = "</persisted-output>"
TOOL_RESULT_CLEARED_MESSAGE: str = "[Old tool result content cleared]"

#: Preview size in bytes for the reference message.
PREVIEW_SIZE_BYTES: int = 2_000

# ---------------------------------------------------------------------------
# GrowthBook stub — always returns the default
# ---------------------------------------------------------------------------


def _get_feature_value_cached(flag_name: str, default: Any) -> Any:  # noqa: ARG001
    """Stub for GrowthBook feature-flag lookup. Always returns *default*."""
    return default


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

# A tool result "content" field: str or list of content blocks.
ToolResultContent = Union[str, List[Dict[str, Any]]]

# A ToolResultBlockParam is a dict with at minimum:
#   {"type": "tool_result", "tool_use_id": str, "content": ...}
ToolResultBlockParam = Dict[str, Any]

# A Message dict (same convention as query_helpers.py).
Message = Dict[str, Any]

# ---------------------------------------------------------------------------
# ContentReplacementState
# ---------------------------------------------------------------------------


@dataclass
class ContentReplacementState:
    """Per-conversation-thread state for the aggregate tool result budget.

    Mirrors TypeScript ``ContentReplacementState``.
    """

    seen_ids: Set[str] = field(default_factory=set)
    replacements: Dict[str, str] = field(default_factory=dict)


def create_content_replacement_state() -> ContentReplacementState:
    """Return a fresh :class:`ContentReplacementState`."""
    return ContentReplacementState()


def clone_content_replacement_state(
    source: ContentReplacementState,
) -> ContentReplacementState:
    """Return a shallow clone of *source* (mutations do not affect the original)."""
    return ContentReplacementState(
        seen_ids=set(source.seen_ids),
        replacements=dict(source.replacements),
    )


# ---------------------------------------------------------------------------
# ContentReplacementRecord
# ---------------------------------------------------------------------------


@dataclass
class ContentReplacementRecord:
    """Serialisable record of one content-replacement decision."""

    kind: str  # "tool-result"
    tool_use_id: str
    replacement: str


# ---------------------------------------------------------------------------
# PersistedToolResult / PersistToolResultError
# ---------------------------------------------------------------------------


@dataclass
class PersistedToolResult:
    """Result of persisting a tool result to disk."""

    filepath: str
    original_size: int
    is_json: bool
    preview: str
    has_more: bool


@dataclass
class PersistToolResultError:
    """Error result when persistence fails."""

    error: str


def is_persist_error(
    result: Union[PersistedToolResult, PersistToolResultError],
) -> bool:
    """Return ``True`` when *result* is a :class:`PersistToolResultError`."""
    return isinstance(result, PersistToolResultError)


# ---------------------------------------------------------------------------
# Session / project directory helpers (lazy imports to avoid circular deps)
# ---------------------------------------------------------------------------


def _get_session_dir(original_cwd: str, session_id: str) -> str:
    """Return ``projectDir/sessionId``."""
    from claude_code.utils.session_storage_portable import get_project_dir

    return os.path.join(get_project_dir(original_cwd), session_id)


def _get_tool_results_dir(original_cwd: str, session_id: str) -> str:
    """Return ``projectDir/sessionId/tool-results``."""
    return os.path.join(_get_session_dir(original_cwd, session_id), TOOL_RESULTS_SUBDIR)


def get_tool_results_dir(original_cwd: str, session_id: str) -> str:
    """Public accessor for the tool-results directory."""
    return _get_tool_results_dir(original_cwd, session_id)


def get_tool_result_path(
    original_cwd: str,
    session_id: str,
    tool_use_id: str,
    is_json: bool,
) -> str:
    """Return the file path for a persisted tool result."""
    ext = "json" if is_json else "txt"
    return os.path.join(_get_tool_results_dir(original_cwd, session_id), f"{tool_use_id}.{ext}")


async def ensure_tool_results_dir(original_cwd: str, session_id: str) -> None:
    """Ensure the session-specific tool-results directory exists."""
    directory = _get_tool_results_dir(original_cwd, session_id)

    def _mkdir():
        os.makedirs(directory, exist_ok=True)

    await asyncio.get_event_loop().run_in_executor(None, _mkdir)


# ---------------------------------------------------------------------------
# Content helpers
# ---------------------------------------------------------------------------


def is_tool_result_content_empty(content: Optional[ToolResultContent]) -> bool:
    """Return ``True`` when *content* is empty or effectively empty."""
    if not content:
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        if not content:
            return True
        return all(
            isinstance(b, dict)
            and b.get("type") == "text"
            and not str(b.get("text", "")).strip()
            for b in content
        )
    return False


def _has_image_block(content: ToolResultContent) -> bool:
    """Return ``True`` when *content* contains an image block."""
    if isinstance(content, list):
        return any(
            isinstance(b, dict) and b.get("type") == "image"
            for b in content
        )
    return False


def _content_size(content: ToolResultContent) -> int:
    """Return the character size of *content*."""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(
            len(b.get("text", "")) if b.get("type") == "text" else 0
            for b in content
            if isinstance(b, dict)
        )
    return 0


def _is_already_compacted(content: Optional[ToolResultContent]) -> bool:
    return isinstance(content, str) and content.startswith(PERSISTED_OUTPUT_TAG)


# ---------------------------------------------------------------------------
# Persistence threshold
# ---------------------------------------------------------------------------


def get_persistence_threshold(
    tool_name: str,
    declared_max_result_size_chars: int,
) -> int:
    """Resolve the effective persistence threshold for *tool_name*.

    GrowthBook overrides are stubbed: always falls back to the hardcoded default.
    Returns ``declared_max_result_size_chars`` unchanged when it is ``float('inf')``.
    """
    if not (declared_max_result_size_chars < float("inf")):
        return declared_max_result_size_chars
    # Stub: no GrowthBook overrides
    return min(declared_max_result_size_chars, DEFAULT_MAX_RESULT_SIZE_CHARS)


# ---------------------------------------------------------------------------
# Preview generation
# ---------------------------------------------------------------------------


def generate_preview(content: str, max_bytes: int) -> Tuple[str, bool]:
    """Return ``(preview, has_more)`` truncated at a newline boundary when possible."""
    if len(content) <= max_bytes:
        return content, False

    truncated = content[:max_bytes]
    last_newline = truncated.rfind("\n")
    cut_point = last_newline if last_newline > max_bytes * 0.5 else max_bytes
    return content[:cut_point], True


# ---------------------------------------------------------------------------
# Core persistence
# ---------------------------------------------------------------------------


async def persist_tool_result(
    content: ToolResultContent,
    tool_use_id: str,
    original_cwd: str,
    session_id: str,
) -> Union[PersistedToolResult, PersistToolResultError]:
    """Persist *content* to disk for *tool_use_id*.

    Returns a :class:`PersistedToolResult` on success or a
    :class:`PersistToolResultError` on failure.
    """
    is_json = isinstance(content, list)

    if is_json:
        # Check for non-text blocks
        if any(
            not (isinstance(b, dict) and b.get("type") == "text")
            for b in content  # type: ignore[union-attr]
        ):
            return PersistToolResultError(
                error="Cannot persist tool results containing non-text content"
            )

    await ensure_tool_results_dir(original_cwd, session_id)
    filepath = get_tool_result_path(original_cwd, session_id, tool_use_id, is_json)

    if is_json:
        content_str = json.dumps(content, indent=2, ensure_ascii=False)
    else:
        content_str = str(content)

    loop = asyncio.get_event_loop()

    def _write():
        # Use exclusive create (x) to skip if already exists
        try:
            with open(filepath, "x", encoding="utf-8") as fh:
                fh.write(content_str)
        except FileExistsError:
            pass  # Already persisted on a prior turn
        except Exception as exc:
            return str(exc)
        return None

    err = await loop.run_in_executor(None, _write)
    if err is not None:
        return PersistToolResultError(error=err)

    preview, has_more = generate_preview(content_str, PREVIEW_SIZE_BYTES)
    return PersistedToolResult(
        filepath=filepath,
        original_size=len(content_str),
        is_json=is_json,
        preview=preview,
        has_more=has_more,
    )


def build_large_tool_result_message(result: PersistedToolResult) -> str:
    """Build the reference message shown to the model for a persisted result."""
    from claude_code.utils.format import format_file_size  # type: ignore

    msg = f"{PERSISTED_OUTPUT_TAG}\n"
    msg += (
        f"Output too large ({format_file_size(result.original_size)}). "
        f"Full output saved to: {result.filepath}\n\n"
    )
    msg += f"Preview (first {format_file_size(PREVIEW_SIZE_BYTES)}):\n"
    msg += result.preview
    msg += "\n...\n" if result.has_more else "\n"
    msg += PERSISTED_OUTPUT_CLOSING_TAG
    return msg


async def maybe_persist_large_tool_result(
    tool_result_block: ToolResultBlockParam,
    tool_name: str,
    original_cwd: str,
    session_id: str,
    persistence_threshold: Optional[int] = None,
) -> ToolResultBlockParam:
    """Handle large tool results by persisting to disk instead of truncating.

    Returns the original block if no persistence is needed, or a modified block
    with content replaced by a reference to the persisted file.
    """
    content = tool_result_block.get("content")

    # Inject placeholder for empty results
    if is_tool_result_content_empty(content):
        return {**tool_result_block, "content": f"({tool_name} completed with no output)"}

    if content is None:
        return tool_result_block

    # Never persist image blocks
    if _has_image_block(content):
        return tool_result_block

    size = _content_size(content)
    threshold = persistence_threshold if persistence_threshold is not None else MAX_TOOL_RESULT_BYTES

    if size <= threshold:
        return tool_result_block

    result = await persist_tool_result(content, tool_result_block["tool_use_id"], original_cwd, session_id)
    if is_persist_error(result):
        return tool_result_block

    assert isinstance(result, PersistedToolResult)
    message = build_large_tool_result_message(result)
    return {**tool_result_block, "content": message}


async def process_tool_result_block(
    tool_name: str,
    max_result_size_chars: int,
    tool_result_block: ToolResultBlockParam,
    original_cwd: str,
    session_id: str,
) -> ToolResultBlockParam:
    """Process a pre-mapped tool result block, applying persistence for large results."""
    threshold = get_persistence_threshold(tool_name, max_result_size_chars)
    return await maybe_persist_large_tool_result(
        tool_result_block, tool_name, original_cwd, session_id, threshold
    )


# ---------------------------------------------------------------------------
# Per-message aggregate budget enforcement
# ---------------------------------------------------------------------------


def get_per_message_budget_limit() -> int:
    """Return the per-message aggregate budget limit.

    GrowthBook override is stubbed — always returns the hardcoded constant.
    """
    return MAX_TOOL_RESULTS_PER_MESSAGE_CHARS


def provision_content_replacement_state(
    initial_messages: Optional[List[Message]] = None,
    initial_content_replacements: Optional[List[ContentReplacementRecord]] = None,
) -> Optional[ContentReplacementState]:
    """Provision replacement state for a new conversation thread.

    Feature flag is stubbed as *disabled* — returns ``None`` (enforcement skipped).
    Override by passing ``initial_messages`` explicitly to force reconstruction.
    """
    # Stub: feature flag disabled → return None (callers skip enforcement)
    return None


def reconstruct_content_replacement_state(
    messages: List[Message],
    records: List[ContentReplacementRecord],
    inherited_replacements: Optional[Dict[str, str]] = None,
) -> ContentReplacementState:
    """Reconstruct replacement state from transcript records on resume."""
    state = create_content_replacement_state()
    candidate_ids = _collect_all_candidate_ids(messages)

    for tid in candidate_ids:
        state.seen_ids.add(tid)

    for r in records:
        if r.kind == "tool-result" and r.tool_use_id in candidate_ids:
            state.replacements[r.tool_use_id] = r.replacement

    if inherited_replacements:
        for tid, repl in inherited_replacements.items():
            if tid in candidate_ids and tid not in state.replacements:
                state.replacements[tid] = repl

    return state


def reconstruct_for_subagent_resume(
    parent_state: Optional[ContentReplacementState],
    resumed_messages: List[Message],
    sidechain_records: List[ContentReplacementRecord],
) -> Optional[ContentReplacementState]:
    """AgentTool-resume variant of :func:`reconstruct_content_replacement_state`."""
    if parent_state is None:
        return None
    return reconstruct_content_replacement_state(
        resumed_messages, sidechain_records, parent_state.replacements
    )


# ---------------------------------------------------------------------------
# Candidate collection helpers
# ---------------------------------------------------------------------------

def _collect_candidates_from_message(message: Message) -> List[Dict[str, Any]]:
    """Extract tool_result candidate blocks from a single user message."""
    if message.get("type") != "user":
        return []
    content = message.get("message", {}).get("content", [])
    if not isinstance(content, list):
        return []
    candidates = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") != "tool_result":
            continue
        c = block.get("content")
        if not c:
            continue
        if _is_already_compacted(c):
            continue
        if _has_image_block(c):
            continue
        candidates.append(
            {
                "tool_use_id": block.get("tool_use_id", ""),
                "content": c,
                "size": _content_size(c),
            }
        )
    return candidates


def _collect_candidates_by_message(
    messages: List[Message],
) -> List[List[Dict[str, Any]]]:
    """Group candidates by API-level user message (consecutive user messages merge)."""
    groups: List[List[Dict[str, Any]]] = []
    current: List[Dict[str, Any]] = []
    seen_asst_ids: Set[str] = set()

    def _flush():
        nonlocal current
        if current:
            groups.append(current)
        current = []

    for msg in messages:
        mtype = msg.get("type")
        if mtype == "user":
            current.extend(_collect_candidates_from_message(msg))
        elif mtype == "assistant":
            asst_id = msg.get("message", {}).get("id", "")
            if asst_id not in seen_asst_ids:
                _flush()
                if asst_id:
                    seen_asst_ids.add(asst_id)
    _flush()
    return groups


def _collect_all_candidate_ids(messages: List[Message]) -> Set[str]:
    return {
        c["tool_use_id"]
        for group in _collect_candidates_by_message(messages)
        for c in group
    }


# ---------------------------------------------------------------------------
# enforceToolResultBudget
# ---------------------------------------------------------------------------


async def enforce_tool_result_budget(
    messages: List[Message],
    state: ContentReplacementState,
    original_cwd: str,
    session_id: str,
    skip_tool_names: Optional[Set[str]] = None,
) -> Tuple[List[Message], List[ContentReplacementRecord]]:
    """Enforce the per-message budget on aggregate tool result size.

    Returns ``(updated_messages, newly_replaced)`` where *newly_replaced* contains
    records for replacements made in **this** call (not re-applications).
    """
    skip_tool_names = skip_tool_names or set()
    limit = get_per_message_budget_limit()
    candidates_by_msg = _collect_candidates_by_message(messages)

    # Build tool_use_id -> tool_name map only when needed
    name_by_id: Dict[str, str] = {}
    if skip_tool_names:
        for msg in messages:
            if msg.get("type") != "assistant":
                continue
            content = msg.get("message", {}).get("content", [])
            if not isinstance(content, list):
                continue
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    name_by_id[block.get("id", "")] = block.get("name", "")

    replacement_map: Dict[str, str] = {}
    to_persist: List[Dict[str, Any]] = []

    for candidates in candidates_by_msg:
        must_reapply = []
        frozen = []
        fresh = []

        for c in candidates:
            tid = c["tool_use_id"]
            if tid in state.replacements:
                must_reapply.append({**c, "replacement": state.replacements[tid]})
            elif tid in state.seen_ids:
                frozen.append(c)
            else:
                fresh.append(c)

        # Re-apply cached replacements
        for c in must_reapply:
            replacement_map[c["tool_use_id"]] = c["replacement"]

        if not fresh:
            for c in candidates:
                state.seen_ids.add(c["tool_use_id"])
            continue

        # Skip tools opted out
        skipped = [c for c in fresh if name_by_id.get(c["tool_use_id"], "") in skip_tool_names]
        eligible = [c for c in fresh if name_by_id.get(c["tool_use_id"], "") not in skip_tool_names]

        for c in skipped:
            state.seen_ids.add(c["tool_use_id"])

        frozen_size = sum(c["size"] for c in frozen)
        fresh_size = sum(c["size"] for c in eligible)

        if frozen_size + fresh_size > limit:
            # Sort by size desc and take until under budget
            sorted_eligible = sorted(eligible, key=lambda x: x["size"], reverse=True)
            selected = []
            remaining = frozen_size + fresh_size
            for c in sorted_eligible:
                if remaining <= limit:
                    break
                selected.append(c)
                remaining -= c["size"]
        else:
            selected = []

        selected_ids = {c["tool_use_id"] for c in selected}
        for c in candidates:
            if c["tool_use_id"] not in selected_ids:
                state.seen_ids.add(c["tool_use_id"])

        to_persist.extend(selected)

    if not replacement_map and not to_persist:
        return messages, []

    # Persist fresh candidates concurrently
    async def _build_replacement(candidate: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
        result = await persist_tool_result(
            candidate["content"], candidate["tool_use_id"], original_cwd, session_id
        )
        if is_persist_error(result):
            return candidate, None
        assert isinstance(result, PersistedToolResult)
        return candidate, build_large_tool_result_message(result)

    persist_results = await asyncio.gather(*[_build_replacement(c) for c in to_persist])

    newly_replaced: List[ContentReplacementRecord] = []
    for candidate, repl_content in persist_results:
        tid = candidate["tool_use_id"]
        state.seen_ids.add(tid)
        if repl_content is None:
            continue
        replacement_map[tid] = repl_content
        state.replacements[tid] = repl_content
        newly_replaced.append(
            ContentReplacementRecord(
                kind="tool-result",
                tool_use_id=tid,
                replacement=repl_content,
            )
        )

    if not replacement_map:
        return messages, []

    # Apply replacements
    def _apply(msgs: List[Message]) -> List[Message]:
        result = []
        for msg in msgs:
            if msg.get("type") != "user":
                result.append(msg)
                continue
            content = msg.get("message", {}).get("content", [])
            if not isinstance(content, list):
                result.append(msg)
                continue
            if not any(
                isinstance(b, dict) and replacement_map.get(b.get("tool_use_id", ""))
                for b in content
            ):
                result.append(msg)
                continue
            new_content = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    repl = replacement_map.get(block.get("tool_use_id", ""))
                    if repl is not None:
                        new_content.append({**block, "content": repl})
                        continue
                new_content.append(block)
            result.append(
                {**msg, "message": {**msg["message"], "content": new_content}}
            )
        return result

    return _apply(messages), newly_replaced


async def apply_tool_result_budget(
    messages: List[Message],
    state: Optional[ContentReplacementState],
    original_cwd: str,
    session_id: str,
    write_to_transcript: Optional[Callable[[List[ContentReplacementRecord]], None]] = None,
    skip_tool_names: Optional[Set[str]] = None,
) -> List[Message]:
    """Query-loop integration point for the aggregate budget.

    Returns *messages* unchanged when *state* is ``None`` (feature disabled).
    """
    if state is None:
        return messages
    updated, newly_replaced = await enforce_tool_result_budget(
        messages, state, original_cwd, session_id, skip_tool_names
    )
    if newly_replaced and write_to_transcript:
        write_to_transcript(newly_replaced)
    return updated

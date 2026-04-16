"""
Main compact service. Ported from services/compact/compact.ts (1705 lines).

This module provides conversation compaction functionality:
- Full compaction (compactConversation): Summarizes entire conversation history
- Partial compaction (partialCompactConversation): Summarizes a slice of messages
- Helper utilities for post-compact file/skill attachment restoration
"""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

POST_COMPACT_MAX_FILES_TO_RESTORE = 5
POST_COMPACT_TOKEN_BUDGET = 50_000
POST_COMPACT_MAX_TOKENS_PER_FILE = 5_000
# Skills can be large. Budget sized to hold ~5 skills at the per-skill cap.
POST_COMPACT_MAX_TOKENS_PER_SKILL = 5_000
POST_COMPACT_SKILLS_TOKEN_BUDGET = 25_000
_MAX_COMPACT_STREAMING_RETRIES = 2

ERROR_MESSAGE_NOT_ENOUGH_MESSAGES = 'Not enough messages to compact.'
ERROR_MESSAGE_PROMPT_TOO_LONG = (
    'Conversation too long. Press esc twice to go up a few messages and try again.'
)
ERROR_MESSAGE_USER_ABORT = 'API Error: Request was aborted.'
ERROR_MESSAGE_INCOMPLETE_RESPONSE = (
    'Compaction interrupted · This may be due to network issues — please try again.'
)

_SKILL_TRUNCATION_MARKER = (
    '\n\n[... skill content truncated for compaction; use Read on the skill path '
    'if you need the full text]'
)
_PTL_RETRY_MARKER = '[earlier conversation truncated for compaction retry]'
_MAX_PTL_RETRIES = 3
_FILE_UNCHANGED_STUB = ''  # populated lazily from FileReadTool prompt constants
_FILE_READ_TOOL_NAME = 'Read'  # default name


def _get_file_read_constants() -> Tuple[str, str]:
    """Lazy import of FileReadTool constants."""
    try:
        from claude_code.tools.file_read_tool.prompt import (
            FILE_READ_TOOL_NAME,
            FILE_UNCHANGED_STUB,
        )
        return FILE_READ_TOOL_NAME, FILE_UNCHANGED_STUB
    except ImportError:
        return 'Read', '__UNCHANGED__'


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class CompactionResult:
    """Result of a compaction operation."""
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


@dataclass
class RecompactionInfo:
    """
    Diagnosis context for auto-compact to disambiguate same-chain loops
    from cross-agent and manual-vs-auto compactions.
    """
    is_recompaction_in_chain: bool
    turns_since_previous_compact: int
    previous_compact_turn_id: Optional[str] = None
    auto_compact_threshold: int = 0
    query_source: Optional[str] = None


# ---------------------------------------------------------------------------
# Image stripping
# ---------------------------------------------------------------------------

def strip_images_from_messages(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Strip image blocks from user messages before sending for compaction.

    Images are not needed for generating a conversation summary and can
    cause the compaction API call itself to hit the prompt-too-long limit.
    Replaces image blocks with a text marker so the summary still notes
    that an image was shared.

    Note: Only user messages contain images (either directly attached or within
    tool_result content from tools). Assistant messages contain text, tool_use,
    and thinking blocks but not images.
    """
    result = []
    for message in messages:
        if message.get('type') != 'user':
            result.append(message)
            continue

        msg = message.get('message', {})
        content = msg.get('content')
        if not isinstance(content, list):
            result.append(message)
            continue

        has_media_block = False
        new_content = []
        for block in content:
            btype = block.get('type', '')
            if btype == 'image':
                has_media_block = True
                new_content.append({'type': 'text', 'text': '[image]'})
            elif btype == 'document':
                has_media_block = True
                new_content.append({'type': 'text', 'text': '[document]'})
            elif btype == 'tool_result' and isinstance(block.get('content'), list):
                tool_has_media = False
                new_tool_content = []
                for item in block['content']:
                    if item.get('type') == 'image':
                        tool_has_media = True
                        new_tool_content.append({'type': 'text', 'text': '[image]'})
                    elif item.get('type') == 'document':
                        tool_has_media = True
                        new_tool_content.append({'type': 'text', 'text': '[document]'})
                    else:
                        new_tool_content.append(item)
                if tool_has_media:
                    has_media_block = True
                    new_content.append({**block, 'content': new_tool_content})
                else:
                    new_content.append(block)
            else:
                new_content.append(block)

        if not has_media_block:
            result.append(message)
        else:
            result.append({
                **message,
                'message': {**msg, 'content': new_content},
            })
    return result


def strip_reinjected_attachments(messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Strip attachment types that are re-injected post-compaction anyway.
    skill_discovery/skill_listing are re-surfaced by resetSentSkillNames() on next turn.
    """
    skill_search_enabled = os.environ.get('EXPERIMENTAL_SKILL_SEARCH', '').lower() in ('1', 'true')
    if skill_search_enabled:
        return [
            m for m in messages
            if not (
                m.get('type') == 'attachment'
                and m.get('attachment', {}).get('type') in ('skill_discovery', 'skill_listing')
            )
        ]
    return messages


# ---------------------------------------------------------------------------
# PTL (prompt-too-long) retry helper
# ---------------------------------------------------------------------------

def truncate_head_for_ptl_retry(
    messages: List[Dict[str, Any]],
    ptl_response: Dict[str, Any],
) -> Optional[List[Dict[str, Any]]]:
    """
    Drops the oldest API-round groups from messages until tokenGap is covered.
    Falls back to dropping 20% of groups when the gap is unparseable.
    Returns None when nothing can be dropped without leaving an empty summarize set.

    This is the last-resort escape hatch for when the compact request itself
    hits prompt-too-long.
    """
    try:
        from claude_code.services.compact.grouping import group_messages_by_api_round
    except ImportError:
        # Fallback: no grouping available
        if len(messages) < 4:
            return None
        drop = max(1, len(messages) // 5)
        return messages[drop:]

    # Strip our own synthetic marker from a previous retry before grouping.
    input_msgs = messages
    if (
        messages
        and messages[0].get('type') == 'user'
        and messages[0].get('isMeta')
        and messages[0].get('message', {}).get('content') == _PTL_RETRY_MARKER
    ):
        input_msgs = messages[1:]

    groups = group_messages_by_api_round(input_msgs)
    if len(groups) < 2:
        return None

    # Try to parse the token gap from the error response
    token_gap = _get_prompt_too_long_token_gap(ptl_response)
    if token_gap is not None:
        acc = 0
        drop_count = 0
        for g in groups:
            acc += rough_token_count_estimation_for_messages(g)
            drop_count += 1
            if acc >= token_gap:
                break
    else:
        drop_count = max(1, int(len(groups) * 0.2))

    # Keep at least one group
    drop_count = min(drop_count, len(groups) - 1)
    if drop_count < 1:
        return None

    sliced = [m for g in groups[drop_count:] for m in g]
    if sliced and sliced[0].get('type') == 'assistant':
        return [
            _create_user_message(_PTL_RETRY_MARKER, is_meta=True),
            *sliced,
        ]
    return sliced


def _get_prompt_too_long_token_gap(response: Dict[str, Any]) -> Optional[int]:
    """Extract token gap from a prompt-too-long error response."""
    try:
        from claude_code.services.api.errors import get_prompt_too_long_token_gap
        return get_prompt_too_long_token_gap(response)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Message helpers
# ---------------------------------------------------------------------------

def _create_user_message(
    content: Any,
    is_meta: bool = False,
    is_compact_summary: bool = False,
    is_visible_in_transcript_only: bool = False,
    summarize_metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Create a user message dict."""
    try:
        from claude_code.utils.messages import create_user_message
        return create_user_message(
            content=content,
            is_meta=is_meta,
            is_compact_summary=is_compact_summary,
            is_visible_in_transcript_only=is_visible_in_transcript_only,
            summarize_metadata=summarize_metadata,
        )
    except ImportError:
        import uuid
        msg: Dict[str, Any] = {
            'type': 'user',
            'uuid': str(uuid.uuid4()),
            'message': {'role': 'user', 'content': content},
        }
        if is_meta:
            msg['isMeta'] = True
        if is_compact_summary:
            msg['isCompactSummary'] = True
        if is_visible_in_transcript_only:
            msg['isVisibleInTranscriptOnly'] = True
        if summarize_metadata:
            msg['summarizeMetadata'] = summarize_metadata
        return msg


def _create_compact_boundary_message(
    trigger: str,
    pre_compact_token_count: int,
    last_message_uuid: Optional[str] = None,
    user_feedback: Optional[str] = None,
    messages_summarized: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a compact boundary marker message."""
    try:
        from claude_code.utils.messages import create_compact_boundary_message
        return create_compact_boundary_message(
            trigger,
            pre_compact_token_count,
            last_message_uuid,
            user_feedback,
            messages_summarized,
        )
    except ImportError:
        import uuid
        msg: Dict[str, Any] = {
            'type': 'system',
            'uuid': str(uuid.uuid4()),
            'subtype': 'compact_boundary',
            'compactMetadata': {
                'trigger': trigger,
                'preCompactTokenCount': pre_compact_token_count,
            },
        }
        if last_message_uuid:
            msg['compactMetadata']['logicalParentUuid'] = last_message_uuid
        if user_feedback:
            msg['compactMetadata']['userFeedback'] = user_feedback
        if messages_summarized is not None:
            msg['compactMetadata']['messagesSummarized'] = messages_summarized
        return msg


def build_post_compact_messages(result: CompactionResult) -> List[Dict[str, Any]]:
    """
    Build the base post-compact messages array from a CompactionResult.
    Ensures consistent ordering across all compaction paths.
    Order: boundaryMarker, summaryMessages, messagesToKeep, attachments, hookResults
    """
    return [
        result.boundary_marker,
        *result.summary_messages,
        *(result.messages_to_keep or []),
        *result.attachments,
        *result.hook_results,
    ]


def annotate_boundary_with_preserved_segment(
    boundary: Dict[str, Any],
    anchor_uuid: str,
    messages_to_keep: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    Annotate a compact boundary with relink metadata for messagesToKeep.

    anchorUuid = what sits immediately before keep[0] in the desired chain:
      - suffix-preserving (reactive/session-memory): last summary message
      - prefix-preserving (partial compact): the boundary itself
    """
    keep = messages_to_keep or []
    if not keep:
        return boundary

    updated = {
        **boundary,
        'compactMetadata': {
            **boundary.get('compactMetadata', {}),
            'preservedSegment': {
                'headUuid': keep[0].get('uuid', ''),
                'anchorUuid': anchor_uuid,
                'tailUuid': keep[-1].get('uuid', ''),
            },
        },
    }
    return updated


def merge_hook_instructions(
    user_instructions: Optional[str],
    hook_instructions: Optional[str],
) -> Optional[str]:
    """
    Merges user-supplied custom instructions with hook-provided instructions.
    User instructions come first; hook instructions are appended.
    Empty strings normalize to None.
    """
    if not hook_instructions:
        return user_instructions or None
    if not user_instructions:
        return hook_instructions
    return f'{user_instructions}\n\n{hook_instructions}'


# ---------------------------------------------------------------------------
# Token estimation helpers
# ---------------------------------------------------------------------------

def rough_token_count_estimation(text: str, bytes_per_token: int = 4) -> int:
    """Estimate token count from text (rough: 4 chars ≈ 1 token)."""
    try:
        from claude_code.services.token_estimation import rough_token_count_estimation as _rte
        return _rte(text)
    except ImportError:
        return max(1, len(text) // bytes_per_token)


def rough_token_count_estimation_for_messages(
    messages: List[Dict[str, Any]],
) -> int:
    """Estimate total token count for a list of messages."""
    try:
        from claude_code.services.token_estimation import rough_token_count_estimation_for_messages as _rtefm
        return _rtefm(messages)
    except ImportError:
        total = 0
        for m in messages:
            content = m.get('message', {}).get('content', '')
            total += rough_token_count_estimation(str(content))
        return total


def token_count_with_estimation(messages: List[Dict[str, Any]]) -> int:
    """Get token count with estimation for message list."""
    try:
        from claude_code.utils.tokens import token_count_with_estimation as _tcwe
        return _tcwe(messages)
    except ImportError:
        return rough_token_count_estimation_for_messages(messages)


def _should_compact(
    messages: List[Dict[str, Any]],
    context_window: int = 200_000,
    threshold: float = 0.85,
) -> bool:
    """
    Heuristic: should we compact now?
    Returns True when estimated token usage exceeds threshold * context_window.
    """
    estimated = token_count_with_estimation(messages)
    return estimated > context_window * threshold


# ---------------------------------------------------------------------------
# Skill truncation
# ---------------------------------------------------------------------------

def _truncate_to_tokens(content: str, max_tokens: int) -> str:
    """
    Truncate content to roughly maxTokens, keeping the head.
    roughTokenCountEstimation uses ~4 chars/token, so char budget = maxTokens * 4
    minus the marker so the result stays within budget.
    """
    if rough_token_count_estimation(content) <= max_tokens:
        return content
    char_budget = max_tokens * 4 - len(_SKILL_TRUNCATION_MARKER)
    return content[:char_budget] + _SKILL_TRUNCATION_MARKER


# ---------------------------------------------------------------------------
# Attachment creation helpers
# ---------------------------------------------------------------------------

def create_attachment_message(attachment: Dict[str, Any]) -> Dict[str, Any]:
    """Create an attachment message dict."""
    try:
        from claude_code.utils.attachments import create_attachment_message as _cam
        return _cam(attachment)
    except ImportError:
        import uuid
        return {
            'type': 'attachment',
            'uuid': str(uuid.uuid4()),
            'attachment': attachment,
        }


def create_plan_attachment_if_needed(
    agent_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Creates a plan file attachment if a plan file exists for the current session.
    This ensures the plan is preserved after compaction.
    """
    try:
        from claude_code.utils.plans import get_plan, get_plan_file_path
        plan_content = get_plan(agent_id)
        if not plan_content:
            return None
        plan_file_path = get_plan_file_path(agent_id)
        return create_attachment_message({
            'type': 'plan_file_reference',
            'planFilePath': plan_file_path,
            'planContent': plan_content,
        })
    except ImportError:
        return None


def create_skill_attachment_if_needed(
    agent_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Creates an attachment for invoked skills to preserve their content across compaction.
    Only includes skills scoped to the given agent.
    """
    try:
        from claude_code.bootstrap.state import get_invoked_skills_for_agent
        invoked_skills = get_invoked_skills_for_agent(agent_id)
    except ImportError:
        return None

    if not invoked_skills:
        return None

    used_tokens = 0
    skills_list = []

    # Sort most-recent-first so budget pressure drops the least-relevant skills
    sorted_skills = sorted(invoked_skills.values(), key=lambda s: getattr(s, 'invoked_at', 0), reverse=True)
    for skill in sorted_skills:
        content = _truncate_to_tokens(
            getattr(skill, 'content', ''),
            POST_COMPACT_MAX_TOKENS_PER_SKILL,
        )
        tokens = rough_token_count_estimation(content)
        if used_tokens + tokens > POST_COMPACT_SKILLS_TOKEN_BUDGET:
            continue
        used_tokens += tokens
        skills_list.append({
            'name': getattr(skill, 'skill_name', ''),
            'path': getattr(skill, 'skill_path', ''),
            'content': content,
        })

    if not skills_list:
        return None

    return create_attachment_message({
        'type': 'invoked_skills',
        'skills': skills_list,
    })


async def create_plan_mode_attachment_if_needed(
    context: Any,
) -> Optional[Dict[str, Any]]:
    """
    Creates a plan_mode attachment if the user is currently in plan mode.
    This ensures the model continues to operate in plan mode after compaction.
    """
    try:
        app_state = context.get_app_state()
        if app_state.tool_permission_context.mode != 'plan':
            return None
        from claude_code.utils.plans import get_plan_file_path, get_plan
        plan_file_path = get_plan_file_path(context.agent_id)
        plan_exists = get_plan(context.agent_id) is not None
        return create_attachment_message({
            'type': 'plan_mode',
            'reminderType': 'full',
            'isSubAgent': bool(context.agent_id),
            'planFilePath': plan_file_path,
            'planExists': plan_exists,
        })
    except Exception:
        return None


async def create_async_agent_attachments_if_needed(
    context: Any,
) -> List[Dict[str, Any]]:
    """
    Creates attachments for async agents so the model knows about them after
    compaction.
    """
    try:
        app_state = context.get_app_state()
        async_agents = [
            task for task in app_state.tasks.values()
            if getattr(task, 'type', None) == 'local_agent'
        ]
    except Exception:
        return []

    attachments = []
    for agent in async_agents:
        if (
            getattr(agent, 'retrieved', False)
            or getattr(agent, 'status', '') == 'pending'
            or getattr(agent, 'agent_id', None) == getattr(context, 'agent_id', None)
        ):
            continue
        try:
            from claude_code.utils.task.disk_output import get_task_output_path
            output_file_path = get_task_output_path(agent.agent_id)
        except ImportError:
            output_file_path = None

        status = getattr(agent, 'status', 'unknown')
        delta_summary = None
        if status == 'running':
            progress = getattr(agent, 'progress', None)
            if progress:
                delta_summary = getattr(progress, 'summary', None)
        else:
            delta_summary = getattr(agent, 'error', None)

        attachments.append(create_attachment_message({
            'type': 'task_status',
            'taskId': getattr(agent, 'agent_id', ''),
            'taskType': 'local_agent',
            'description': getattr(agent, 'description', ''),
            'status': status,
            'deltaSummary': delta_summary,
            'outputFilePath': output_file_path,
        }))

    return attachments


async def create_post_compact_file_attachments(
    read_file_state: Dict[str, Dict[str, Any]],
    tool_use_context: Any,
    max_files: int,
    preserved_messages: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """
    Creates attachment messages for recently accessed files to restore them
    after compaction.

    Files already present as Read tool results in preservedMessages are skipped.

    :param read_file_state: The current file state tracking recently read files
    :param tool_use_context: The tool use context for calling FileReadTool
    :param max_files: Maximum number of files to restore (default: 5)
    :param preserved_messages: Messages kept post-compact; Read results here are skipped
    :returns: Array of attachment messages for the most recently accessed files
              that fit within token budget
    """
    if preserved_messages is None:
        preserved_messages = []

    try:
        from claude_code.utils.path import expand_path
    except ImportError:
        def expand_path(p: str) -> str:  # type: ignore[misc]
            return os.path.expanduser(os.path.expandvars(p))

    preserved_read_paths = _collect_read_tool_file_paths(preserved_messages, expand_path)

    def should_exclude(filename: str) -> bool:
        return _should_exclude_from_post_compact_restore(
            filename, getattr(tool_use_context, 'agent_id', None), expand_path
        )

    recent_files = sorted(
        [
            (fname, state)
            for fname, state in read_file_state.items()
            if not should_exclude(fname)
            and expand_path(fname) not in preserved_read_paths
        ],
        key=lambda x: x[1].get('timestamp', 0),
        reverse=True,
    )[:max_files]

    results: List[Optional[Dict[str, Any]]] = []
    for fname, _state in recent_files:
        try:
            from claude_code.utils.attachments import generate_file_attachment
            attachment = await generate_file_attachment(
                fname,
                {**tool_use_context.__dict__, 'fileReadingLimits': {'maxTokens': POST_COMPACT_MAX_TOKENS_PER_FILE}},
                'tengu_post_compact_file_restore_success',
                'tengu_post_compact_file_restore_error',
                'compact',
            )
            if attachment:
                results.append(create_attachment_message(attachment))
            else:
                results.append(None)
        except Exception:
            results.append(None)

    used_tokens = 0
    final_attachments: List[Dict[str, Any]] = []
    for result in results:
        if result is None:
            continue
        tokens = rough_token_count_estimation(str(result))
        if used_tokens + tokens <= POST_COMPACT_TOKEN_BUDGET:
            used_tokens += tokens
            final_attachments.append(result)

    return final_attachments


def _collect_read_tool_file_paths(
    messages: List[Dict[str, Any]],
    expand_path: Callable[[str], str],
) -> Set[str]:
    """
    Scan messages for Read tool_use blocks and collect their file_path inputs.

    Skips Reads whose tool_result is a dedup stub — the stub points at an
    earlier full Read that may have been compacted away, so we want
    createPostCompactFileAttachments to re-inject the real content.
    """
    file_read_tool_name, file_unchanged_stub = _get_file_read_constants()

    # First pass: collect stub ids
    stub_ids: Set[str] = set()
    for message in messages:
        if message.get('type') != 'user':
            continue
        content = message.get('message', {}).get('content', [])
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                block.get('type') == 'tool_result'
                and isinstance(block.get('content'), str)
                and block['content'].startswith(file_unchanged_stub)
            ):
                stub_ids.add(block.get('tool_use_id', ''))

    # Second pass: collect file paths from non-stub Read tool_use blocks
    paths: Set[str] = set()
    for message in messages:
        if message.get('type') != 'assistant':
            continue
        content = message.get('message', {}).get('content', [])
        if not isinstance(content, list):
            continue
        for block in content:
            if (
                block.get('type') != 'tool_use'
                or block.get('name') != file_read_tool_name
                or block.get('id', '') in stub_ids
            ):
                continue
            input_data = block.get('input', {})
            if isinstance(input_data, dict) and isinstance(input_data.get('file_path'), str):
                paths.add(expand_path(input_data['file_path']))

    return paths


def _should_exclude_from_post_compact_restore(
    filename: str,
    agent_id: Optional[str],
    expand_path: Callable[[str], str],
) -> bool:
    """Check whether a file should be excluded from post-compact restoration."""
    normalized = expand_path(filename)

    # Exclude plan files
    try:
        from claude_code.utils.plans import get_plan_file_path
        plan_path = expand_path(get_plan_file_path(agent_id))
        if normalized == plan_path:
            return True
    except Exception:
        pass

    # Exclude all types of claude.md / memory files
    try:
        from claude_code.utils.memory.types import MEMORY_TYPE_VALUES
        from claude_code.utils.config import get_memory_path
        for mtype in MEMORY_TYPE_VALUES:
            if normalized == expand_path(get_memory_path(mtype)):
                return True
    except Exception:
        pass

    return False


# ---------------------------------------------------------------------------
# Main compact function
# ---------------------------------------------------------------------------

async def compact_messages(
    messages: List[Dict[str, Any]],
    context: Any = None,
    model: str = '',
    focus: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """
    Compact a message list by summarizing older messages.
    High-level wrapper that returns the post-compact message list,
    or None if compaction is not possible/needed.
    """
    if not messages:
        return None
    if context is None:
        return None
    try:
        result = await compact_conversation(
            messages=messages,
            context=context,
            cache_safe_params={},
            suppress_follow_up_questions=False,
            custom_instructions=focus,
            is_auto_compact=False,
        )
        return build_post_compact_messages(result)
    except Exception:
        return None


def should_compact(
    messages: List[Dict[str, Any]],
    context_window: int = 200_000,
    threshold: float = 0.85,
) -> bool:
    """
    Heuristic: should we compact now?
    Returns True when estimated token usage exceeds threshold * context_window.
    """
    return _should_compact(messages, context_window, threshold)


async def compact_conversation(
    messages: List[Dict[str, Any]],
    context: Any,
    cache_safe_params: Dict[str, Any],
    suppress_follow_up_questions: bool,
    custom_instructions: Optional[str] = None,
    is_auto_compact: bool = False,
    recompaction_info: Optional[RecompactionInfo] = None,
) -> CompactionResult:
    """
    Creates a compact version of a conversation by summarizing older messages
    and preserving recent conversation history.

    Ported from compactConversation() in compact.ts.
    """
    if not messages:
        raise ValueError(ERROR_MESSAGE_NOT_ENOUGH_MESSAGES)

    pre_compact_token_count = token_count_with_estimation(messages)

    try:
        context.set_sdk_status('compacting')
    except Exception:
        pass

    # Execute PreCompact hooks
    hook_instructions: Optional[str] = None
    user_display_message: Optional[str] = None
    try:
        from claude_code.utils.hooks import execute_pre_compact_hooks
        hook_result = await execute_pre_compact_hooks(
            {
                'trigger': 'auto' if is_auto_compact else 'manual',
                'customInstructions': custom_instructions,
            },
            getattr(context, 'abort_signal', None),
        )
        hook_instructions = hook_result.get('newCustomInstructions')
        user_display_message = hook_result.get('userDisplayMessage')
    except Exception:
        pass

    custom_instructions = merge_hook_instructions(custom_instructions, hook_instructions)

    # Get compact prompt
    try:
        from claude_code.services.compact.prompt import get_compact_prompt, get_compact_user_summary_message
        compact_prompt_text = get_compact_prompt(custom_instructions)
    except ImportError:
        compact_prompt_text = (
            'Please summarize the above conversation, preserving all important context, '
            'decisions, and information that would be needed to continue the conversation.'
        )

    summary_request = _create_user_message(compact_prompt_text)

    # Stream summary (simplified — actual API call requires context)
    summary: Optional[str] = None
    summary_response: Optional[Dict[str, Any]] = None
    ptl_attempts = 0
    messages_to_summarize = list(messages)

    for _ in range(_MAX_PTL_RETRIES + 1):
        try:
            summary_response, summary = await _stream_compact_summary(
                messages=messages_to_summarize,
                summary_request=summary_request,
                context=context,
                pre_compact_token_count=pre_compact_token_count,
                cache_safe_params=cache_safe_params,
            )
            if summary and not _is_prompt_too_long(summary):
                break
            if summary and _is_prompt_too_long(summary):
                ptl_attempts += 1
                truncated = truncate_head_for_ptl_retry(messages_to_summarize, summary_response or {})
                if truncated is None or ptl_attempts > _MAX_PTL_RETRIES:
                    raise ValueError(ERROR_MESSAGE_PROMPT_TOO_LONG)
                messages_to_summarize = truncated
                cache_safe_params = {
                    **cache_safe_params,
                    'forkContextMessages': truncated,
                }
            else:
                break
        except Exception as e:
            if str(e) in (ERROR_MESSAGE_PROMPT_TOO_LONG, ERROR_MESSAGE_USER_ABORT, ERROR_MESSAGE_INCOMPLETE_RESPONSE):
                raise
            raise

    if not summary:
        raise ValueError('Failed to generate conversation summary - response did not contain valid text content')

    # Store file state before clearing
    read_file_state: Dict[str, Any] = {}
    try:
        read_file_state = dict(context.read_file_state)
        context.read_file_state.clear()
        if hasattr(context, 'loaded_nested_memory_paths') and context.loaded_nested_memory_paths:
            context.loaded_nested_memory_paths.clear()
    except Exception:
        pass

    # Create post-compact attachments
    file_attachments, async_agent_attachments = await asyncio.gather(
        create_post_compact_file_attachments(
            read_file_state,
            context,
            POST_COMPACT_MAX_FILES_TO_RESTORE,
        ),
        create_async_agent_attachments_if_needed(context),
    )

    post_compact_file_attachments: List[Dict[str, Any]] = [
        *file_attachments,
        *async_agent_attachments,
    ]

    plan_attachment = create_plan_attachment_if_needed(getattr(context, 'agent_id', None))
    if plan_attachment:
        post_compact_file_attachments.append(plan_attachment)

    plan_mode_attachment = await create_plan_mode_attachment_if_needed(context)
    if plan_mode_attachment:
        post_compact_file_attachments.append(plan_mode_attachment)

    skill_attachment = create_skill_attachment_if_needed(getattr(context, 'agent_id', None))
    if skill_attachment:
        post_compact_file_attachments.append(skill_attachment)

    # Re-announce delta attachments
    try:
        from claude_code.utils.attachments import (
            get_deferred_tools_delta_attachment,
            get_agent_listing_delta_attachment,
            get_mcp_instructions_delta_attachment,
        )
        for att in get_deferred_tools_delta_attachment(
            getattr(context, 'options', {}).get('tools', []) if hasattr(context, 'options') else [],
            getattr(context, 'options', {}).get('mainLoopModel', '') if hasattr(context, 'options') else '',
            [],
            {'callSite': 'compact_full'},
        ):
            post_compact_file_attachments.append(create_attachment_message(att))
    except Exception:
        pass

    # Execute session start hooks
    hook_messages: List[Dict[str, Any]] = []
    try:
        from claude_code.utils.session_start import process_session_start_hooks
        hook_messages = await process_session_start_hooks('compact', {
            'model': getattr(context, 'options', {}).get('mainLoopModel', '') if hasattr(context, 'options') else '',
        })
    except Exception:
        pass

    # Build summary message
    try:
        from claude_code.utils.session_storage import get_transcript_path
        transcript_path = get_transcript_path()
    except Exception:
        transcript_path = None

    try:
        from claude_code.services.compact.prompt import get_compact_user_summary_message
        summary_content = get_compact_user_summary_message(
            summary,
            suppress_follow_up_questions,
            transcript_path,
        )
    except ImportError:
        summary_content = f'<summary>\n{summary}\n</summary>'

    boundary_marker = _create_compact_boundary_message(
        'auto' if is_auto_compact else 'manual',
        pre_compact_token_count,
        messages[-1].get('uuid') if messages else None,
    )

    summary_messages: List[Dict[str, Any]] = [
        _create_user_message(
            summary_content,
            is_compact_summary=True,
            is_visible_in_transcript_only=True,
        )
    ]

    # Post-compact hooks
    post_compact_user_display_message: Optional[str] = None
    try:
        from claude_code.utils.hooks import execute_post_compact_hooks
        post_hook_result = await execute_post_compact_hooks(
            {
                'trigger': 'auto' if is_auto_compact else 'manual',
                'compactSummary': summary,
            },
            getattr(context, 'abort_signal', None),
        )
        post_compact_user_display_message = post_hook_result.get('userDisplayMessage')
    except Exception:
        pass

    combined_user_display = ' '.join(filter(None, [user_display_message, post_compact_user_display_message])) or None

    try:
        context.set_sdk_status(None)
    except Exception:
        pass

    return CompactionResult(
        boundary_marker=boundary_marker,
        summary_messages=summary_messages,
        attachments=post_compact_file_attachments,
        hook_results=hook_messages,
        user_display_message=combined_user_display,
        pre_compact_token_count=pre_compact_token_count,
    )


def _is_prompt_too_long(text: str) -> bool:
    """Check if the response text starts with a prompt-too-long error."""
    try:
        from claude_code.services.api.errors import PROMPT_TOO_LONG_ERROR_MESSAGE
        return text.startswith(PROMPT_TOO_LONG_ERROR_MESSAGE)
    except ImportError:
        return text.startswith('API Error:') and 'too long' in text.lower()


async def _stream_compact_summary(
    messages: List[Dict[str, Any]],
    summary_request: Dict[str, Any],
    context: Any,
    pre_compact_token_count: int,
    cache_safe_params: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Stream a compact summary response. Returns (response_msg, summary_text).
    Falls back to None, None if streaming is unavailable.
    """
    try:
        from claude_code.services.api.claude import query_model_with_streaming
        from claude_code.utils.messages import (
            get_messages_after_compact_boundary,
            normalize_messages_for_api,
            get_assistant_message_text,
        )

        tools = getattr(context, 'options', {}).get('tools', []) if hasattr(context, 'options') else []
        main_loop_model = getattr(context, 'options', {}).get('mainLoopModel', '') if hasattr(context, 'options') else ''

        api_messages = normalize_messages_for_api(
            strip_images_from_messages(
                strip_reinjected_attachments([
                    *get_messages_after_compact_boundary(messages),
                    summary_request,
                ])
            ),
            tools,
        )

        response = None
        async for event in query_model_with_streaming(
            messages=api_messages,
            system_prompt=[{'type': 'text', 'text': 'You are a helpful AI assistant tasked with summarizing conversations.'}],
            thinking_config={'type': 'disabled'},
            tools=[],
            signal=getattr(context, 'abort_signal', None),
            options={
                'model': main_loop_model,
                'query_source': 'compact',
            },
        ):
            if isinstance(event, dict) and event.get('type') == 'assistant':
                response = event

        if response:
            text = get_assistant_message_text(response)
            return response, text
    except Exception:
        pass

    return None, None


async def partial_compact_conversation(
    all_messages: List[Dict[str, Any]],
    pivot_index: int,
    context: Any,
    cache_safe_params: Dict[str, Any],
    user_feedback: Optional[str] = None,
    direction: str = 'from',
) -> CompactionResult:
    """
    Performs a partial compaction around the selected message index.

    Direction 'from': summarizes messages after the index, keeps earlier ones.
      Prompt cache for kept (earlier) messages is preserved.
    Direction 'up_to': summarizes messages before the index, keeps later ones.
      Prompt cache is invalidated since the summary precedes the kept messages.
    """
    if direction == 'up_to':
        messages_to_summarize = all_messages[:pivot_index]
        # 'up_to' must strip old compact boundaries/summaries
        messages_to_keep = [
            m for m in all_messages[pivot_index:]
            if m.get('type') != 'progress'
            and not _is_compact_boundary(m)
            and not (m.get('type') == 'user' and m.get('isCompactSummary'))
        ]
    else:
        messages_to_summarize = all_messages[pivot_index:]
        messages_to_keep = [
            m for m in all_messages[:pivot_index]
            if m.get('type') != 'progress'
        ]

    if not messages_to_summarize:
        if direction == 'up_to':
            raise ValueError('Nothing to summarize before the selected message.')
        else:
            raise ValueError('Nothing to summarize after the selected message.')

    pre_compact_token_count = token_count_with_estimation(all_messages)

    try:
        context.set_sdk_status('compacting')
    except Exception:
        pass

    # Execute PreCompact hooks
    hook_instructions: Optional[str] = None
    try:
        from claude_code.utils.hooks import execute_pre_compact_hooks
        hook_result = await execute_pre_compact_hooks(
            {'trigger': 'manual', 'customInstructions': None},
            getattr(context, 'abort_signal', None),
        )
        hook_instructions = hook_result.get('newCustomInstructions')
    except Exception:
        pass

    # Merge hook instructions with user feedback
    custom_instructions: Optional[str] = None
    if hook_instructions and user_feedback:
        custom_instructions = f'{hook_instructions}\n\nUser context: {user_feedback}'
    elif hook_instructions:
        custom_instructions = hook_instructions
    elif user_feedback:
        custom_instructions = f'User context: {user_feedback}'

    # Get partial compact prompt
    try:
        from claude_code.services.compact.prompt import get_partial_compact_prompt
        compact_prompt_text = get_partial_compact_prompt(custom_instructions, direction)
    except ImportError:
        compact_prompt_text = (
            'Please summarize the selected portion of the conversation, '
            'preserving all important context and decisions.'
        )

    summary_request = _create_user_message(compact_prompt_text)

    # Stream summary
    api_messages = messages_to_summarize if direction == 'up_to' else all_messages
    ptl_attempts = 0
    summary: Optional[str] = None
    summary_response: Optional[Dict[str, Any]] = None

    for _ in range(_MAX_PTL_RETRIES + 1):
        try:
            summary_response, summary = await _stream_compact_summary(
                messages=api_messages,
                summary_request=summary_request,
                context=context,
                pre_compact_token_count=pre_compact_token_count,
                cache_safe_params=cache_safe_params,
            )
            if summary and not _is_prompt_too_long(summary):
                break
            if summary and _is_prompt_too_long(summary):
                ptl_attempts += 1
                truncated = truncate_head_for_ptl_retry(api_messages, summary_response or {})
                if truncated is None or ptl_attempts > _MAX_PTL_RETRIES:
                    raise ValueError(ERROR_MESSAGE_PROMPT_TOO_LONG)
                api_messages = truncated
                cache_safe_params = {
                    **cache_safe_params,
                    'forkContextMessages': truncated,
                }
            else:
                break
        except Exception as e:
            if str(e) in (ERROR_MESSAGE_PROMPT_TOO_LONG, ERROR_MESSAGE_USER_ABORT, ERROR_MESSAGE_INCOMPLETE_RESPONSE):
                raise
            raise

    if not summary:
        raise ValueError('Failed to generate conversation summary - response did not contain valid text content')

    # Clear file state
    read_file_state: Dict[str, Any] = {}
    try:
        read_file_state = dict(context.read_file_state)
        context.read_file_state.clear()
        if hasattr(context, 'loaded_nested_memory_paths') and context.loaded_nested_memory_paths:
            context.loaded_nested_memory_paths.clear()
    except Exception:
        pass

    # Create post-compact attachments
    file_attachments, async_agent_attachments = await asyncio.gather(
        create_post_compact_file_attachments(
            read_file_state,
            context,
            POST_COMPACT_MAX_FILES_TO_RESTORE,
            messages_to_keep,
        ),
        create_async_agent_attachments_if_needed(context),
    )

    post_compact_file_attachments: List[Dict[str, Any]] = [
        *file_attachments,
        *async_agent_attachments,
    ]

    plan_attachment = create_plan_attachment_if_needed(getattr(context, 'agent_id', None))
    if plan_attachment:
        post_compact_file_attachments.append(plan_attachment)

    plan_mode_attachment = await create_plan_mode_attachment_if_needed(context)
    if plan_mode_attachment:
        post_compact_file_attachments.append(plan_mode_attachment)

    skill_attachment = create_skill_attachment_if_needed(getattr(context, 'agent_id', None))
    if skill_attachment:
        post_compact_file_attachments.append(skill_attachment)

    # Session start hooks
    hook_messages: List[Dict[str, Any]] = []
    try:
        from claude_code.utils.session_start import process_session_start_hooks
        hook_messages = await process_session_start_hooks('compact', {
            'model': getattr(context, 'options', {}).get('mainLoopModel', '') if hasattr(context, 'options') else '',
        })
    except Exception:
        pass

    # Post compact hook
    post_compact_user_display_message: Optional[str] = None
    try:
        from claude_code.utils.hooks import execute_post_compact_hooks
        post_hook_result = await execute_post_compact_hooks(
            {'trigger': 'manual', 'compactSummary': summary},
            getattr(context, 'abort_signal', None),
        )
        post_compact_user_display_message = post_hook_result.get('userDisplayMessage')
    except Exception:
        pass

    # Determine last pre-compact UUID
    if direction == 'up_to':
        last_msgs = [m for m in all_messages[:pivot_index] if m.get('type') != 'progress']
        last_pre_compact_uuid = last_msgs[-1].get('uuid') if last_msgs else None
    else:
        last_pre_compact_uuid = messages_to_keep[-1].get('uuid') if messages_to_keep else None

    boundary_marker = _create_compact_boundary_message(
        'manual',
        pre_compact_token_count,
        last_pre_compact_uuid,
        user_feedback,
        len(messages_to_summarize),
    )

    # Build summary message
    try:
        from claude_code.utils.session_storage import get_transcript_path
        transcript_path = get_transcript_path()
    except Exception:
        transcript_path = None

    try:
        from claude_code.services.compact.prompt import get_compact_user_summary_message
        summary_content = get_compact_user_summary_message(summary, False, transcript_path)
    except ImportError:
        summary_content = f'<summary>\n{summary}\n</summary>'

    summary_messages: List[Dict[str, Any]]
    if messages_to_keep:
        summary_messages = [
            _create_user_message(
                summary_content,
                is_compact_summary=True,
                summarize_metadata={
                    'messagesSummarized': len(messages_to_summarize),
                    'userContext': user_feedback,
                    'direction': direction,
                },
            )
        ]
    else:
        summary_messages = [
            _create_user_message(
                summary_content,
                is_compact_summary=True,
                is_visible_in_transcript_only=True,
            )
        ]

    # Anchor for preserved segment
    anchor_uuid: str
    if direction == 'up_to':
        anchor_uuid = summary_messages[-1].get('uuid', boundary_marker.get('uuid', '')) if summary_messages else boundary_marker.get('uuid', '')
    else:
        anchor_uuid = boundary_marker.get('uuid', '')

    annotated_boundary = annotate_boundary_with_preserved_segment(
        boundary_marker,
        anchor_uuid,
        messages_to_keep if messages_to_keep else None,
    )

    try:
        context.set_sdk_status(None)
    except Exception:
        pass

    return CompactionResult(
        boundary_marker=annotated_boundary,
        summary_messages=summary_messages,
        messages_to_keep=messages_to_keep if messages_to_keep else None,
        attachments=post_compact_file_attachments,
        hook_results=hook_messages,
        user_display_message=post_compact_user_display_message,
        pre_compact_token_count=pre_compact_token_count,
    )


def _is_compact_boundary(message: Dict[str, Any]) -> bool:
    """Check if a message is a compact boundary marker."""
    try:
        from claude_code.utils.messages import is_compact_boundary_message
        return is_compact_boundary_message(message)
    except ImportError:
        return (
            message.get('type') == 'system'
            and message.get('subtype') == 'compact_boundary'
        )


def create_compact_can_use_tool() -> Callable[..., Any]:
    """Create a canUseTool function that denies all tool use during compaction."""
    async def _can_use_tool(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        return {
            'behavior': 'deny',
            'message': 'Tool use is not allowed during compaction',
            'decisionReason': {
                'type': 'other',
                'reason': 'compaction agent should only produce text summary',
            },
        }
    return _can_use_tool

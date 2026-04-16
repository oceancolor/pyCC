# 原始 TS: utils/attachments.ts
"""
Attachment generation: produces typed Attachment objects that are later
rendered into Anthropic API message blocks.

This module is a faithful Python port of the 3997-line TypeScript original.
Most heavy-lifting functions require runtime context objects (ToolUseContext,
AppState, etc.) that live in other parts of the Python port.  Where those
objects are not yet fully ported, the functions return empty lists / None
(safe degradation) and are annotated with # TODO.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from os.path import dirname, relpath, splitext, abspath
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Dict,
    List,
    Literal,
    Optional,
    Set,
    Sequence,
    Tuple,
    Union,
)

# ---------------------------------------------------------------------------
# Optional / guarded imports
# ---------------------------------------------------------------------------
try:
    from claude_code.utils.string_utils import count_char_in_string
except ImportError:
    def count_char_in_string(s: str, char: str) -> int:  # type: ignore[misc]
        return s.count(char)

try:
    from claude_code.utils.array import uniq
except ImportError:
    def uniq(lst: list) -> list:  # type: ignore[misc]
        seen: set = set()
        result = []
        for item in lst:
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result

try:
    from claude_code.utils.errors import is_enoent, to_error
except ImportError:
    def is_enoent(e: Exception) -> bool:  # type: ignore[misc]
        return isinstance(e, FileNotFoundError)
    def to_error(e: Any) -> Exception:  # type: ignore[misc]
        if isinstance(e, Exception):
            return e
        return Exception(str(e))

try:
    from claude_code.utils.env_utils import is_env_truthy
except ImportError:
    def is_env_truthy(v: Optional[str]) -> bool:  # type: ignore[misc]
        return str(v).lower() in {"1", "true", "yes"} if v else False

if TYPE_CHECKING:
    # Heavy runtime objects — only imported during type-checking.
    from claude_code.tool import ToolUseContext  # noqa: F401

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TODO_REMINDER_CONFIG: Dict[str, int] = {
    "TURNS_SINCE_WRITE": 10,
    "TURNS_BETWEEN_REMINDERS": 10,
}

PLAN_MODE_ATTACHMENT_CONFIG: Dict[str, int] = {
    "TURNS_BETWEEN_ATTACHMENTS": 5,
    "FULL_REMINDER_EVERY_N_ATTACHMENTS": 5,
}

AUTO_MODE_ATTACHMENT_CONFIG: Dict[str, int] = {
    "TURNS_BETWEEN_ATTACHMENTS": 5,
    "FULL_REMINDER_EVERY_N_ATTACHMENTS": 5,
}

MAX_MEMORY_LINES: int = 200

# 5 files × 4 KB per turn (bounded injection)
MAX_MEMORY_BYTES: int = 4096

RELEVANT_MEMORIES_CONFIG: Dict[str, int] = {
    # Cumulative session cap: ~3 full injections before stopping prefetch
    "MAX_SESSION_BYTES": 60 * 1024,
}

VERIFY_PLAN_REMINDER_CONFIG: Dict[str, int] = {
    "TURNS_BETWEEN_REMINDERS": 10,
}

# Filtered listing max when skill-search is enabled
FILTERED_LISTING_MAX: int = 30

INLINE_NOTIFICATION_MODES: Set[str] = {"prompt", "task-notification"}

# ---------------------------------------------------------------------------
# Type aliases / TypedDict definitions
#
# TypeScript union types → Python TypedDict.  The "type" discriminant
# field is kept as a Literal so isinstance-free dispatch works via
# `attachment["type"]` lookups.
# ---------------------------------------------------------------------------

# We use plain Dict[str, Any] as the base for Attachment members to avoid
# circular deps on unported modules; the real types are described below
# as docstrings mirroring the TS interfaces.

FileReadToolOutput = Any  # 原始 TS: Output from FileReadTool


class FileAttachment(dict):
    """
    type: 'file'
    filename: str
    content: FileReadToolOutput
    truncated: Optional[bool]
    displayPath: str
    """


class CompactFileReferenceAttachment(dict):
    """
    type: 'compact_file_reference'
    filename: str
    displayPath: str
    """


class PDFReferenceAttachment(dict):
    """
    type: 'pdf_reference'
    filename: str
    pageCount: int
    fileSize: int
    displayPath: str
    """


class AlreadyReadFileAttachment(dict):
    """
    type: 'already_read_file'
    filename: str
    content: FileReadToolOutput
    truncated: Optional[bool]
    displayPath: str
    """


class AgentMentionAttachment(dict):
    """
    type: 'agent_mention'
    agentType: str
    """


class AsyncHookResponseAttachment(dict):
    """
    type: 'async_hook_response'
    processId: str
    hookName: str
    hookEvent: str
    toolName: Optional[str]
    response: Any
    stdout: str
    stderr: str
    exitCode: Optional[int]
    """


# HookAttachment subtypes
class HookCancelledAttachment(dict):
    """type: 'hook_cancelled' ..."""


class HookNonBlockingErrorAttachment(dict):
    """type: 'hook_non_blocking_error' ..."""


class HookErrorDuringExecutionAttachment(dict):
    """type: 'hook_error_during_execution' ..."""


class HookSuccessAttachment(dict):
    """type: 'hook_success' ..."""


class HookPermissionDecisionAttachment(dict):
    """type: 'hook_permission_decision' ..."""


class HookSystemMessageAttachment(dict):
    """type: 'hook_system_message' ..."""


class TeammateMailboxAttachment(dict):
    """
    type: 'teammate_mailbox'
    messages: List[dict]  # from, text, timestamp, color?, summary?
    """


class TeamContextAttachment(dict):
    """
    type: 'team_context'
    agentId: str
    agentName: str
    teamName: str
    teamConfigPath: str
    taskListPath: str
    """


# The full Attachment type — in Python we use Dict[str, Any] at runtime
# with the "type" key as discriminant.
Attachment = Dict[str, Any]

# AttachmentMessage wraps an attachment with metadata
AttachmentMessage = Dict[str, Any]

# MemoryPrefetch handle
MemoryPrefetch = Dict[str, Any]

# ---------------------------------------------------------------------------
# Module-level mutable state (mirrors TS module-scope vars)
# ---------------------------------------------------------------------------

# Maps agentId ('' = main thread) → set of sent skill names
_sent_skill_names: Dict[str, Set[str]] = {}

# Whether to suppress the next skill listing injection
_suppress_next: bool = False

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_cwd() -> str:
    """Return the current working directory. Mirrors getCwd() in TS."""
    try:
        from claude_code.utils.cwd import get_cwd  # type: ignore[import]
        return get_cwd()
    except ImportError:
        return os.getcwd()


def _relative(base: str, path: str) -> str:
    """Return path relative to base, falling back to path."""
    try:
        return relpath(path, base)
    except ValueError:
        return path


def _get_session_id() -> str:
    try:
        from claude_code.bootstrap.state import get_session_id  # type: ignore[import]
        return get_session_id()
    except ImportError:
        return str(uuid.uuid4())


def _get_original_cwd() -> str:
    try:
        from claude_code.bootstrap.state import get_original_cwd  # type: ignore[import]
        return get_original_cwd()
    except ImportError:
        return os.getcwd()


def _get_local_iso_date() -> str:
    """Return local date in ISO format YYYY-MM-DD."""
    return datetime.now().strftime("%Y-%m-%d")


# Last emitted date for date-change detection
_last_emitted_date: Optional[str] = None


def _get_last_emitted_date() -> Optional[str]:
    return _last_emitted_date


def _set_last_emitted_date(date: str) -> None:
    global _last_emitted_date
    _last_emitted_date = date


# ---------------------------------------------------------------------------
# Attachment type predicates
# ---------------------------------------------------------------------------


def _is_tool_result_block(b: Any) -> bool:
    return (
        isinstance(b, dict)
        and b.get("type") == "tool_result"
        and isinstance(b.get("tool_use_id"), str)
    )


def _has_tool_result_content(content: Any) -> bool:
    """Check whether a user message's content contains tool_result blocks."""
    return isinstance(content, list) and any(
        _is_tool_result_block(item) for item in content
    )


def _is_human_turn(message: Dict[str, Any]) -> bool:
    """True if this message is a human (non-meta, non-tool-result user) turn."""
    try:
        from claude_code.utils.message_predicates import is_human_turn  # type: ignore[import]
        return is_human_turn(message)
    except ImportError:
        return (
            message.get("type") == "user"
            and not message.get("isMeta", False)
            and not _has_tool_result_content(
                message.get("message", {}).get("content", [])
            )
        )


def _is_thinking_message(message: Dict[str, Any]) -> bool:
    try:
        from claude_code.utils.messages import is_thinking_message  # type: ignore[import]
        return is_thinking_message(message)
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# At-mention parsing / extraction
# ---------------------------------------------------------------------------


def extract_at_mentioned_files(content: str) -> List[str]:
    """
    Extract filenames mentioned with @ symbol, including line range syntax.
    Mirrors extractAtMentionedFiles() in TS.
    """
    quoted_at_mention_re = re.compile(r'(?:^|\s)@"([^"]+)"')
    regular_at_mention_re = re.compile(r'(?:^|\s)@([^\s]+)\b')

    quoted_matches: List[str] = []
    regular_matches: List[str] = []

    for m in quoted_at_mention_re.finditer(content):
        val = m.group(1)
        if val and not val.endswith(" (agent)"):
            quoted_matches.append(val)

    for m in regular_at_mention_re.finditer(content):
        filename = m.group(1)
        if filename and not filename.startswith('"'):
            regular_matches.append(filename)

    return uniq(quoted_matches + regular_matches)


def extract_mcp_resource_mentions(content: str) -> List[str]:
    """
    Extract MCP resources mentioned with @ symbol in format @server:uri.
    Mirrors extractMcpResourceMentions() in TS.
    """
    at_mention_re = re.compile(r'(?:^|\s)@([^\s]+:[^\s]+)\b')
    matches = at_mention_re.findall(content)
    return uniq(matches)


def extract_agent_mentions(content: str) -> List[str]:
    """
    Extract agent mentions in two formats:
    1. @agent-<type>  (legacy/manual)
    2. @"<type> (agent)"  (from autocomplete)
    Mirrors extractAgentMentions() in TS.
    """
    results: List[str] = []

    # Quoted format: @"<type> (agent)"
    quoted_re = re.compile(r'(?:^|\s)@"([\w:.@-]+) \(agent\)"')
    for m in quoted_re.finditer(content):
        if m.group(1):
            results.append(m.group(1))

    # Unquoted format: @agent-<type>
    unquoted_re = re.compile(r'(?:^|\s)(@agent-[\w:.@-]+)')
    for m in unquoted_re.finditer(content):
        val = m.group(1)
        # strip leading whitespace that leaked in
        results.append(val.lstrip())

    return uniq(results)


def parse_at_mentioned_file_lines(
    mention: str,
) -> Dict[str, Any]:
    """
    Parse mentions like 'file.txt#L10-20', 'file.txt#heading', or 'file.txt'.
    Returns dict with keys: filename, lineStart (optional), lineEnd (optional).
    Mirrors parseAtMentionedFileLines() in TS.
    """
    m = re.match(r'^([^#]+)(?:#L(\d+)(?:-(\d+))?)?(?:#[^#]*)?$', mention)
    if not m:
        return {"filename": mention}

    filename, line_start_str, line_end_str = m.group(1), m.group(2), m.group(3)
    line_start = int(line_start_str) if line_start_str else None
    line_end = int(line_end_str) if line_end_str else line_start
    result: Dict[str, Any] = {"filename": filename or mention}
    if line_start is not None:
        result["lineStart"] = line_start
    if line_end is not None:
        result["lineEnd"] = line_end
    return result


# ---------------------------------------------------------------------------
# Date-change attachments
# ---------------------------------------------------------------------------


def get_date_change_attachments(
    messages: Optional[List[Dict[str, Any]]],
) -> List[Attachment]:
    """
    Detects when the local date has changed since the last turn and emits an
    attachment to notify the model.
    Mirrors getDateChangeAttachments() in TS. Exported for testing.
    """
    current_date = _get_local_iso_date()
    last_date = _get_last_emitted_date()

    if last_date is None:
        _set_last_emitted_date(current_date)
        return []

    if current_date == last_date:
        return []

    _set_last_emitted_date(current_date)
    return [{"type": "date_change", "newDate": current_date}]


# ---------------------------------------------------------------------------
# Plan mode helpers
# ---------------------------------------------------------------------------


def _get_plan_mode_attachment_turn_count(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Count human turns since the last plan_mode attachment."""
    turns_since_last = 0
    found = False

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if (
            msg.get("type") == "user"
            and not msg.get("isMeta", False)
            and not _has_tool_result_content(
                msg.get("message", {}).get("content", [])
            )
        ):
            turns_since_last += 1
        elif msg.get("type") == "attachment" and msg.get("attachment", {}).get(
            "type"
        ) in ("plan_mode", "plan_mode_reentry"):
            found = True
            break

    return {"turnCount": turns_since_last, "foundPlanModeAttachment": found}


def _count_plan_mode_attachments_since_last_exit(
    messages: List[Dict[str, Any]],
) -> int:
    count = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("type") == "attachment":
            atype = msg.get("attachment", {}).get("type")
            if atype == "plan_mode_exit":
                break
            if atype == "plan_mode":
                count += 1
    return count


async def _get_plan_mode_attachments(
    messages: Optional[List[Dict[str, Any]]],
    tool_use_context: Any,
) -> List[Attachment]:
    """
    Generate plan_mode reminder attachments.
    Mirrors getPlanModeAttachments() in TS.
    """
    try:
        app_state = tool_use_context.get_app_state()
        permission_context = app_state.get("toolPermissionContext", {})
        if permission_context.get("mode") != "plan":
            return []

        if messages:
            turn_info = _get_plan_mode_attachment_turn_count(messages)
            if (
                turn_info["foundPlanModeAttachment"]
                and turn_info["turnCount"]
                < PLAN_MODE_ATTACHMENT_CONFIG["TURNS_BETWEEN_ATTACHMENTS"]
            ):
                return []

        # plan file path
        plan_file_path = _get_plan_file_path(
            getattr(tool_use_context, "agent_id", None)
        )
        existing_plan = _get_plan(getattr(tool_use_context, "agent_id", None))
        attachments: List[Attachment] = []

        try:
            from claude_code.bootstrap.state import (  # type: ignore[import]
                has_exited_plan_mode_in_session,
                set_has_exited_plan_mode,
            )
            if has_exited_plan_mode_in_session() and existing_plan is not None:
                attachments.append(
                    {"type": "plan_mode_reentry", "planFilePath": plan_file_path}
                )
                set_has_exited_plan_mode(False)
        except ImportError:
            pass

        attachment_count = _count_plan_mode_attachments_since_last_exit(messages or []) + 1
        reminder_type: str = (
            "full"
            if attachment_count
            % PLAN_MODE_ATTACHMENT_CONFIG["FULL_REMINDER_EVERY_N_ATTACHMENTS"]
            == 1
            else "sparse"
        )

        attachments.append(
            {
                "type": "plan_mode",
                "reminderType": reminder_type,
                "isSubAgent": bool(getattr(tool_use_context, "agent_id", None)),
                "planFilePath": plan_file_path,
                "planExists": existing_plan is not None,
            }
        )
        return attachments
    except Exception:
        return []


async def _get_plan_mode_exit_attachment(
    tool_use_context: Any,
) -> List[Attachment]:
    """Return a plan_mode_exit attachment if we just exited plan mode."""
    try:
        from claude_code.bootstrap.state import (  # type: ignore[import]
            needs_plan_mode_exit_attachment,
            set_needs_plan_mode_exit_attachment,
        )
        if not needs_plan_mode_exit_attachment():
            return []

        app_state = tool_use_context.get_app_state()
        if app_state.get("toolPermissionContext", {}).get("mode") == "plan":
            set_needs_plan_mode_exit_attachment(False)
            return []

        set_needs_plan_mode_exit_attachment(False)
        plan_file_path = _get_plan_file_path(
            getattr(tool_use_context, "agent_id", None)
        )
        plan_exists = _get_plan(getattr(tool_use_context, "agent_id", None)) is not None
        return [{"type": "plan_mode_exit", "planFilePath": plan_file_path, "planExists": plan_exists}]
    except ImportError:
        return []
    except Exception:
        return []


def _get_plan_file_path(agent_id: Optional[str]) -> str:
    try:
        from claude_code.utils.plans import get_plan_file_path  # type: ignore[import]
        return get_plan_file_path(agent_id)
    except ImportError:
        return ""


def _get_plan(agent_id: Optional[str]) -> Any:
    try:
        from claude_code.utils.plans import get_plan  # type: ignore[import]
        return get_plan(agent_id)
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Auto mode helpers
# ---------------------------------------------------------------------------


def _get_auto_mode_attachment_turn_count(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    turns_since_last = 0
    found = False

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if (
            msg.get("type") == "user"
            and not msg.get("isMeta", False)
            and not _has_tool_result_content(
                msg.get("message", {}).get("content", [])
            )
        ):
            turns_since_last += 1
        elif msg.get("type") == "attachment":
            atype = msg.get("attachment", {}).get("type")
            if atype == "auto_mode":
                found = True
                break
            if atype == "auto_mode_exit":
                break

    return {"turnCount": turns_since_last, "foundAutoModeAttachment": found}


def _count_auto_mode_attachments_since_last_exit(
    messages: List[Dict[str, Any]],
) -> int:
    count = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("type") == "attachment":
            atype = msg.get("attachment", {}).get("type")
            if atype == "auto_mode_exit":
                break
            if atype == "auto_mode":
                count += 1
    return count


async def _get_auto_mode_attachments(
    messages: Optional[List[Dict[str, Any]]],
    tool_use_context: Any,
) -> List[Attachment]:
    try:
        app_state = tool_use_context.get_app_state()
        permission_context = app_state.get("toolPermissionContext", {})
        in_auto = permission_context.get("mode") == "auto"
        if not in_auto:
            return []

        if messages:
            turn_info = _get_auto_mode_attachment_turn_count(messages)
            if (
                turn_info["foundAutoModeAttachment"]
                and turn_info["turnCount"]
                < AUTO_MODE_ATTACHMENT_CONFIG["TURNS_BETWEEN_ATTACHMENTS"]
            ):
                return []

        attachment_count = _count_auto_mode_attachments_since_last_exit(messages or []) + 1
        reminder_type: str = (
            "full"
            if attachment_count
            % AUTO_MODE_ATTACHMENT_CONFIG["FULL_REMINDER_EVERY_N_ATTACHMENTS"]
            == 1
            else "sparse"
        )
        return [{"type": "auto_mode", "reminderType": reminder_type}]
    except Exception:
        return []


async def _get_auto_mode_exit_attachment(
    tool_use_context: Any,
) -> List[Attachment]:
    try:
        from claude_code.bootstrap.state import (  # type: ignore[import]
            needs_auto_mode_exit_attachment,
            set_needs_auto_mode_exit_attachment,
        )
        if not needs_auto_mode_exit_attachment():
            return []

        app_state = tool_use_context.get_app_state()
        if app_state.get("toolPermissionContext", {}).get("mode") == "auto":
            set_needs_auto_mode_exit_attachment(False)
            return []

        set_needs_auto_mode_exit_attachment(False)
        return [{"type": "auto_mode_exit"}]
    except ImportError:
        return []
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Ultrathink
# ---------------------------------------------------------------------------


def _get_ultrathink_effort_attachment(
    input_text: Optional[str],
) -> List[Attachment]:
    try:
        from claude_code.utils.thinking import (  # type: ignore[import]
            is_ultrathink_enabled,
            has_ultrathink_keyword,
        )
        if not is_ultrathink_enabled() or not input_text or not has_ultrathink_keyword(input_text):
            return []
    except ImportError:
        return []
    return [{"type": "ultrathink_effort", "level": "high"}]


# ---------------------------------------------------------------------------
# Token / budget usage attachments
# ---------------------------------------------------------------------------


def _get_token_usage_attachment(
    messages: List[Dict[str, Any]],
    model: str,
) -> List[Attachment]:
    if not is_env_truthy(os.environ.get("CLAUDE_CODE_ENABLE_TOKEN_USAGE_ATTACHMENT")):
        return []
    try:
        from claude_code.utils.tokens import token_count_from_last_api_response  # type: ignore[import]
        from claude_code.services.compact.auto_compact import get_effective_context_window_size  # type: ignore[import]
        context_window = get_effective_context_window_size(model)
        used_tokens = token_count_from_last_api_response(messages)
        return [
            {
                "type": "token_usage",
                "used": used_tokens,
                "total": context_window,
                "remaining": context_window - used_tokens,
            }
        ]
    except ImportError:
        return []


def _get_output_token_usage_attachment() -> List[Attachment]:
    try:
        from claude_code.bootstrap.state import (  # type: ignore[import]
            get_current_turn_token_budget,
            get_turn_output_tokens,
            get_total_output_tokens,
        )
        budget = get_current_turn_token_budget()
        if budget is None or budget <= 0:
            return []
        return [
            {
                "type": "output_token_usage",
                "turn": get_turn_output_tokens(),
                "session": get_total_output_tokens(),
                "budget": budget,
            }
        ]
    except ImportError:
        return []


def _get_max_budget_usd_attachment(
    max_budget_usd: Optional[float],
) -> List[Attachment]:
    if max_budget_usd is None:
        return []
    try:
        from claude_code.bootstrap.state import get_total_cost_usd  # type: ignore[import]
        used_cost = get_total_cost_usd()
    except ImportError:
        used_cost = 0.0
    return [
        {
            "type": "budget_usd",
            "used": used_cost,
            "total": max_budget_usd,
            "remaining": max_budget_usd - used_cost,
        }
    ]


# ---------------------------------------------------------------------------
# Output style
# ---------------------------------------------------------------------------


def _get_output_style_attachment() -> List[Attachment]:
    try:
        from claude_code.utils.settings.settings import get_settings_deprecated  # type: ignore[import]
        settings = get_settings_deprecated()
        output_style = (settings or {}).get("outputStyle", "default")
        if output_style == "default":
            return []
        return [{"type": "output_style", "style": output_style}]
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Critical system reminder
# ---------------------------------------------------------------------------


def _get_critical_system_reminder_attachment(
    tool_use_context: Any,
) -> List[Attachment]:
    reminder = getattr(tool_use_context, "critical_system_reminder_experimental", None)
    if not reminder:
        return []
    return [{"type": "critical_system_reminder", "content": reminder}]


# ---------------------------------------------------------------------------
# Compaction / context-efficiency reminders
# ---------------------------------------------------------------------------


def get_compaction_reminder_attachment(
    messages: List[Dict[str, Any]],
    model: str,
) -> List[Attachment]:
    """
    Compaction reminder for auto-compact enabled sessions near context limit.
    Mirrors getCompactionReminderAttachment() in TS. Exported for compact.ts.
    """
    try:
        from claude_code.services.compact.auto_compact import (  # type: ignore[import]
            is_auto_compact_enabled,
            get_effective_context_window_size,
        )
        from claude_code.utils.context import get_context_window_for_model  # type: ignore[import]
        from claude_code.utils.tokens import token_count_with_estimation  # type: ignore[import]
        from claude_code.bootstrap.state import get_sdk_betas  # type: ignore[import]

        if not is_auto_compact_enabled():
            return []

        context_window = get_context_window_for_model(model, get_sdk_betas())
        if context_window < 1_000_000:
            return []

        effective_window = get_effective_context_window_size(model)
        used_tokens = token_count_with_estimation(messages)
        if used_tokens < effective_window * 0.25:
            return []

        return [{"type": "compaction_reminder"}]
    except ImportError:
        return []


def get_context_efficiency_attachment(
    messages: List[Dict[str, Any]],
) -> List[Attachment]:
    """
    Context-efficiency nudge. Mirrors getContextEfficiencyAttachment() in TS.
    """
    try:
        from claude_code.services.compact.snip_compact import (  # type: ignore[import]
            is_snip_runtime_enabled,
            should_nudge_for_snips,
        )
        if not is_snip_runtime_enabled():
            return []
        if not should_nudge_for_snips(messages):
            return []
        return [{"type": "context_efficiency"}]
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Deferred tools delta
# ---------------------------------------------------------------------------


def get_deferred_tools_delta_attachment(
    tools: Any,
    model: str,
    messages: Optional[List[Dict[str, Any]]],
    scan_context: Optional[Any] = None,
) -> List[Attachment]:
    """
    Mirrors getDeferredToolsDeltaAttachment() in TS.
    Exported for compact.ts — gate must be identical at both call sites.
    """
    try:
        from claude_code.utils.tool_search import (  # type: ignore[import]
            is_deferred_tools_delta_enabled,
            is_tool_search_enabled_optimistic,
            model_supports_tool_reference,
            is_tool_search_tool_available,
            get_deferred_tools_delta,
        )
        if not is_deferred_tools_delta_enabled():
            return []
        if not is_tool_search_enabled_optimistic():
            return []
        if not model_supports_tool_reference(model):
            return []
        if not is_tool_search_tool_available(tools):
            return []
        delta = get_deferred_tools_delta(tools, messages or [], scan_context)
        if not delta:
            return []
        result = {"type": "deferred_tools_delta"}
        result.update(delta)
        return [result]
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Agent listing delta
# ---------------------------------------------------------------------------


def get_agent_listing_delta_attachment(
    tool_use_context: Any,
    messages: Optional[List[Dict[str, Any]]],
) -> List[Attachment]:
    """
    Diff current agent pool against already-announced agents.
    Mirrors getAgentListingDeltaAttachment() in TS.
    Exported for compact.ts.
    """
    try:
        from claude_code.tools.agent_tool.prompt import (  # type: ignore[import]
            should_inject_agent_list_in_messages,
            format_agent_line,
        )
        from claude_code.tools.agent_tool.constants import AGENT_TOOL_NAME  # type: ignore[import]
        from claude_code.utils.permissions.permissions import filter_denied_agents  # type: ignore[import]
        from claude_code.tools.agent_tool.load_agents_dir import filter_agents_by_mcp_requirements  # type: ignore[import]
        from claude_code.utils.auth import get_subscription_type  # type: ignore[import]
        from claude_code.utils.mcp_string_utils import mcp_info_from_string  # type: ignore[import]
        from claude_code.tool import tool_matches_name  # type: ignore[import]

        if not should_inject_agent_list_in_messages():
            return []

        if not any(tool_matches_name(t, AGENT_TOOL_NAME) for t in (tool_use_context.options.tools or [])):
            return []

        agent_defs = tool_use_context.options.agent_definitions
        active_agents = agent_defs.active_agents
        allowed_agent_types = agent_defs.allowed_agent_types

        mcp_servers: Set[str] = set()
        for tool in (tool_use_context.options.tools or []):
            info = mcp_info_from_string(tool.name)
            if info:
                mcp_servers.add(info["serverName"])

        permission_context = tool_use_context.get_app_state().get("toolPermissionContext", {})
        filtered = filter_denied_agents(
            filter_agents_by_mcp_requirements(active_agents, list(mcp_servers)),
            permission_context,
            AGENT_TOOL_NAME,
        )
        if allowed_agent_types:
            filtered = [a for a in filtered if a.agent_type in allowed_agent_types]

        # Reconstruct announced set from prior deltas
        announced: Set[str] = set()
        for msg in (messages or []):
            if msg.get("type") != "attachment":
                continue
            att = msg.get("attachment", {})
            if att.get("type") != "agent_listing_delta":
                continue
            for t in att.get("addedTypes", []):
                announced.add(t)
            for t in att.get("removedTypes", []):
                announced.discard(t)

        current_types = {a.agent_type for a in filtered}
        added = [a for a in filtered if a.agent_type not in announced]
        removed = [t for t in announced if t not in current_types]

        if not added and not removed:
            return []

        added.sort(key=lambda a: a.agent_type)
        removed.sort()

        return [
            {
                "type": "agent_listing_delta",
                "addedTypes": [a.agent_type for a in added],
                "addedLines": [format_agent_line(a) for a in added],
                "removedTypes": removed,
                "isInitial": len(announced) == 0,
                "showConcurrencyNote": get_subscription_type() != "pro",
            }
        ]
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# MCP instructions delta
# ---------------------------------------------------------------------------


def get_mcp_instructions_delta_attachment(
    mcp_clients: List[Any],
    tools: Any,
    model: str,
    messages: Optional[List[Dict[str, Any]]],
) -> List[Attachment]:
    """
    Mirrors getMcpInstructionsDeltaAttachment() in TS.
    Exported for compact.ts.
    """
    try:
        from claude_code.utils.mcp_instructions_delta import (  # type: ignore[import]
            is_mcp_instructions_delta_enabled,
            get_mcp_instructions_delta,
        )
        if not is_mcp_instructions_delta_enabled():
            return []
        delta = get_mcp_instructions_delta(mcp_clients, messages or [], [])
        if not delta:
            return []
        result = {"type": "mcp_instructions_delta"}
        result.update(delta)
        return [result]
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Directory / file helpers
# ---------------------------------------------------------------------------


def get_directories_to_process(
    target_path: str,
    original_cwd: str,
) -> Dict[str, List[str]]:
    """
    Compute directories to process for nested memory file loading.
    Returns: { 'nestedDirs': [...], 'cwdLevelDirs': [...] }
    Mirrors getDirectoriesToProcess() in TS.
    """
    target_dir = dirname(abspath(target_path))
    nested_dirs: List[str] = []
    current_dir = target_dir

    # Walk from target dir up to original_cwd
    while current_dir != original_cwd:
        parent = dirname(current_dir)
        if parent == current_dir:  # hit filesystem root
            break
        if current_dir.startswith(original_cwd):
            nested_dirs.append(current_dir)
        current_dir = parent

    # Reverse: order from CWD down to target
    nested_dirs.reverse()

    # CWD-level dirs: from root to CWD
    cwd_level_dirs: List[str] = []
    current_dir = original_cwd
    while True:
        parent = dirname(current_dir)
        if parent == current_dir:
            break
        cwd_level_dirs.append(current_dir)
        current_dir = parent

    cwd_level_dirs.reverse()

    return {"nestedDirs": nested_dirs, "cwdLevelDirs": cwd_level_dirs}


# ---------------------------------------------------------------------------
# Memory file helpers
# ---------------------------------------------------------------------------


def memory_files_to_attachments(
    memory_files: List[Any],
    tool_use_context: Any,
    trigger_file_path: Optional[str] = None,
) -> List[Attachment]:
    """
    Converts memory files to attachments, filtering already-loaded files.
    Mirrors memoryFilesToAttachments() in TS. Exported for testing.
    """
    attachments: List[Attachment] = []
    cwd = _get_cwd()

    loaded_paths: Optional[Set[str]] = getattr(
        tool_use_context, "loaded_nested_memory_paths", None
    )
    read_file_state: Any = getattr(tool_use_context, "read_file_state", None)

    for memory_file in memory_files:
        path = getattr(memory_file, "path", None) or memory_file.get("path", "")

        if loaded_paths is not None and path in loaded_paths:
            continue
        if read_file_state is not None:
            try:
                if read_file_state.has(path):
                    continue
            except Exception:
                if path in read_file_state:
                    continue

        content = getattr(memory_file, "content", None) or memory_file.get("content", "")
        attachments.append(
            {
                "type": "nested_memory",
                "path": path,
                "content": memory_file,
                "displayPath": _relative(cwd, path),
            }
        )

        if loaded_paths is not None:
            loaded_paths.add(path)

        if read_file_state is not None:
            raw_content = (
                getattr(memory_file, "raw_content", None)
                or memory_file.get("rawContent")
                or content
            )
            differs_from_disk = (
                getattr(memory_file, "content_differs_from_disk", False)
                or memory_file.get("contentDiffersFromDisk", False)
            )
            try:
                read_file_state.set(
                    path,
                    {
                        "content": raw_content if differs_from_disk else content,
                        "timestamp": _now_ms(),
                        "offset": None,
                        "limit": None,
                        "isPartialView": differs_from_disk,
                    },
                )
            except Exception:
                pass

    return attachments


def _now_ms() -> int:
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def memory_header(path: str, mtime_ms: int) -> str:
    """
    Header string for a relevant-memory block.
    Mirrors memoryHeader() in TS.
    """
    try:
        from claude_code.memdir.memory_age import (  # type: ignore[import]
            memory_freshness_text,
            memory_age,
        )
        staleness = memory_freshness_text(mtime_ms)
        if staleness:
            return f"{staleness}\n\nMemory: {path}:"
        return f"Memory (saved {memory_age(mtime_ms)}): {path}:"
    except ImportError:
        return f"Memory: {path}:"


async def read_memories_for_surfacing(
    selected: Sequence[Dict[str, Any]],
    signal: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """
    Read relevance-ranked memory files for injection as <system-reminder> attachments.
    Mirrors readMemoriesForSurfacing() in TS.
    """
    import asyncio

    results = []
    for item in selected:
        file_path = item.get("path", "")
        mtime_ms = item.get("mtimeMs", 0)
        try:
            content_lines = Path(file_path).read_text(errors="replace").splitlines()
            truncated_by_lines = len(content_lines) > MAX_MEMORY_LINES
            lines_to_read = content_lines[:MAX_MEMORY_LINES]
            content = "\n".join(lines_to_read)

            # Byte limit enforcement
            truncated_by_bytes = len(content.encode("utf-8")) > MAX_MEMORY_BYTES
            if truncated_by_bytes:
                content = content.encode("utf-8")[:MAX_MEMORY_BYTES].decode("utf-8", errors="replace")

            truncated = truncated_by_lines or truncated_by_bytes
            if truncated:
                limit_desc = (
                    f"{MAX_MEMORY_BYTES} byte limit"
                    if truncated_by_bytes
                    else f"first {MAX_MEMORY_LINES} lines"
                )
                content += (
                    f"\n\n> This memory file was truncated ({limit_desc}). "
                    f"Use the Read tool to view the complete file at: {file_path}"
                )

            results.append(
                {
                    "path": file_path,
                    "content": content,
                    "mtimeMs": mtime_ms,
                    "header": memory_header(file_path, mtime_ms),
                    "limit": len(lines_to_read) if truncated else None,
                }
            )
        except Exception:
            continue

    return results


def collect_surfaced_memories(
    messages: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Scan messages for past relevant_memories attachments.
    Returns { 'paths': Set[str], 'totalBytes': int }.
    Mirrors collectSurfacedMemories() in TS. Exported.
    """
    paths: Set[str] = set()
    total_bytes = 0
    for m in messages:
        if m.get("type") == "attachment":
            att = m.get("attachment", {})
            if att.get("type") == "relevant_memories":
                for mem in att.get("memories", []):
                    p = mem.get("path", "")
                    paths.add(p)
                    total_bytes += len(mem.get("content", ""))
    return {"paths": paths, "totalBytes": total_bytes}


def filter_duplicate_memory_attachments(
    attachments: List[Attachment],
    read_file_state: Any,
) -> List[Attachment]:
    """
    Filters prefetched memory attachments to exclude memories already in context.
    Mirrors filterDuplicateMemoryAttachments() in TS. Exported.
    """
    result: List[Attachment] = []
    for attachment in attachments:
        if attachment.get("type") != "relevant_memories":
            result.append(attachment)
            continue

        try:
            def _has(p: str) -> bool:
                try:
                    return read_file_state.has(p)
                except Exception:
                    return p in read_file_state

            filtered = [m for m in attachment.get("memories", []) if not _has(m.get("path", ""))]
        except Exception:
            filtered = attachment.get("memories", [])

        for m in filtered:
            try:
                read_file_state.set(
                    m["path"],
                    {
                        "content": m.get("content", ""),
                        "timestamp": m.get("mtimeMs", 0),
                        "offset": None,
                        "limit": m.get("limit"),
                    },
                )
            except Exception:
                pass

        if filtered:
            result.append({**attachment, "memories": filtered})

    return result


# ---------------------------------------------------------------------------
# Relevant memory prefetch
# ---------------------------------------------------------------------------


def start_relevant_memory_prefetch(
    messages: Sequence[Dict[str, Any]],
    tool_use_context: Any,
) -> Optional[MemoryPrefetch]:
    """
    Starts the relevant memory search as an async prefetch.
    Mirrors startRelevantMemoryPrefetch() in TS.
    """
    try:
        from claude_code.memdir.paths import is_auto_memory_enabled  # type: ignore[import]
        if not is_auto_memory_enabled():
            return None
    except ImportError:
        return None

    return None  # Full async prefetch machinery — not yet ported


# ---------------------------------------------------------------------------
# Recent successful tools collector
# ---------------------------------------------------------------------------


def collect_recent_successful_tools(
    messages: Sequence[Dict[str, Any]],
    last_user_message: Dict[str, Any],
) -> List[str]:
    """
    Return names of tools that succeeded (never errored) since the previous
    real turn boundary.
    Mirrors collectRecentSuccessfulTools() in TS.
    """
    use_id_to_name: Dict[str, str] = {}
    result_by_use_id: Dict[str, bool] = {}  # True = errored

    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if not m:
            continue
        if _is_human_turn(m) and m is not last_user_message:
            break
        if m.get("type") == "assistant":
            content = m.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        use_id_to_name[block["id"]] = block["name"]
        elif m.get("type") == "user":
            content = m.get("message", {}).get("content", [])
            if isinstance(content, list):
                for block in content:
                    if _is_tool_result_block(block):
                        result_by_use_id[block["tool_use_id"]] = block.get("is_error", False) is True

    failed: Set[str] = set()
    succeeded: Set[str] = set()
    for uid, name in use_id_to_name.items():
        errored = result_by_use_id.get(uid)
        if errored is None:
            continue
        if errored:
            failed.add(name)
        else:
            succeeded.add(name)

    return [t for t in succeeded if t not in failed]


# ---------------------------------------------------------------------------
# Verify plan reminder
# ---------------------------------------------------------------------------


def get_verify_plan_reminder_turn_count(
    messages: List[Dict[str, Any]],
) -> int:
    """
    Count human turns since plan_mode_exit attachment.
    Mirrors getVerifyPlanReminderTurnCount() in TS. Exported.
    """
    turn_count = 0
    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if _is_human_turn(msg):
            turn_count += 1
        if msg.get("type") == "attachment" and msg.get("attachment", {}).get("type") == "plan_mode_exit":
            return turn_count
    return 0


async def _get_verify_plan_reminder_attachment(
    messages: Optional[List[Dict[str, Any]]],
    tool_use_context: Any,
) -> List[Attachment]:
    if (
        os.environ.get("USER_TYPE") != "ant"
        or not is_env_truthy(os.environ.get("CLAUDE_CODE_VERIFY_PLAN"))
    ):
        return []

    try:
        app_state = tool_use_context.get_app_state()
        pending = app_state.get("pendingPlanVerification")
        if not pending or pending.get("verificationStarted") or pending.get("verificationCompleted"):
            return []

        if messages:
            turn_count = get_verify_plan_reminder_turn_count(messages)
            if (
                turn_count == 0
                or turn_count % VERIFY_PLAN_REMINDER_CONFIG["TURNS_BETWEEN_REMINDERS"] != 0
            ):
                return []

        return [{"type": "verify_plan_reminder"}]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Skill listing
# ---------------------------------------------------------------------------


def reset_sent_skill_names() -> None:
    """
    Called when the skill set genuinely changes (plugin reload, etc.).
    Mirrors resetSentSkillNames() in TS.
    """
    global _suppress_next
    _sent_skill_names.clear()
    _suppress_next = False


def suppress_next_skill_listing() -> None:
    """
    Suppress the next skill-listing injection (e.g., on --resume).
    Mirrors suppressNextSkillListing() in TS.
    """
    global _suppress_next
    _suppress_next = True


def filter_to_bundled_and_mcp(commands: List[Any]) -> List[Any]:
    """
    Filter skills to bundled + MCP only (used when skill-search is enabled).
    Mirrors filterToBundledAndMcp() in TS. Exported.
    """
    filtered = [c for c in commands if getattr(c, "loaded_from", None) in ("bundled", "mcp")]
    if len(filtered) > FILTERED_LISTING_MAX:
        return [c for c in filtered if getattr(c, "loaded_from", None) == "bundled"]
    return filtered


async def _get_skill_listing_attachments(
    tool_use_context: Any,
) -> List[Attachment]:
    global _suppress_next

    if os.environ.get("NODE_ENV") == "test":
        return []

    try:
        from claude_code.tools.skill_tool.constants import SKILL_TOOL_NAME  # type: ignore[import]
        from claude_code.tool import tool_matches_name  # type: ignore[import]
        from claude_code.commands import get_skill_tool_commands, get_mcp_skill_commands  # type: ignore[import]
        from claude_code.tools.skill_tool.prompt import format_commands_within_budget  # type: ignore[import]
        from claude_code.utils.context import get_context_window_for_model  # type: ignore[import]
        from claude_code.bootstrap.state import get_sdk_betas  # type: ignore[import]
        from claude_code.bootstrap.state import get_project_root  # type: ignore[import]

        if not any(tool_matches_name(t, SKILL_TOOL_NAME) for t in (tool_use_context.options.tools or [])):
            return []

        cwd = get_project_root()
        local_commands = await get_skill_tool_commands(cwd)
        mcp_skills = get_mcp_skill_commands(
            tool_use_context.get_app_state().get("mcp", {}).get("commands", [])
        )
        if mcp_skills:
            seen_names: Set[str] = set()
            all_commands = []
            for cmd in local_commands + mcp_skills:
                if cmd.name not in seen_names:
                    seen_names.add(cmd.name)
                    all_commands.append(cmd)
        else:
            all_commands = list(local_commands)

        agent_key = getattr(tool_use_context, "agent_id", None) or ""
        if agent_key not in _sent_skill_names:
            _sent_skill_names[agent_key] = set()
        sent = _sent_skill_names[agent_key]

        if _suppress_next:
            _suppress_next = False
            for cmd in all_commands:
                sent.add(cmd.name)
            return []

        new_skills = [cmd for cmd in all_commands if cmd.name not in sent]
        if not new_skills:
            return []

        is_initial = len(sent) == 0
        for cmd in new_skills:
            sent.add(cmd.name)

        context_window_tokens = get_context_window_for_model(
            tool_use_context.options.main_loop_model, get_sdk_betas()
        )
        content = format_commands_within_budget(new_skills, context_window_tokens)
        return [
            {
                "type": "skill_listing",
                "content": content,
                "skillCount": len(new_skills),
                "isInitial": is_initial,
            }
        ]
    except (ImportError, Exception):
        return []


# ---------------------------------------------------------------------------
# Queued command attachments
# ---------------------------------------------------------------------------


async def get_queued_command_attachments(
    queued_commands: Optional[List[Any]],
) -> List[Attachment]:
    """
    Convert queued commands to attachment dicts.
    Mirrors getQueuedCommandAttachments() in TS. Exported.
    """
    if not queued_commands:
        return []

    filtered = [c for c in queued_commands if getattr(c, "mode", None) in INLINE_NOTIFICATION_MODES]
    results = []
    for cmd in filtered:
        pasted_contents = getattr(cmd, "pasted_contents", None)
        image_blocks = await _build_image_content_blocks(pasted_contents)
        value = getattr(cmd, "value", "")
        if image_blocks:
            text_value = value if isinstance(value, str) else _extract_text_content(value)
            prompt: Any = [{"type": "text", "text": text_value}] + image_blocks
        else:
            prompt = value

        results.append(
            {
                "type": "queued_command",
                "prompt": prompt,
                "source_uuid": getattr(cmd, "uuid", None),
                "imagePasteIds": _get_image_paste_ids(pasted_contents),
                "commandMode": getattr(cmd, "mode", None),
                "origin": getattr(cmd, "origin", None),
                "isMeta": getattr(cmd, "is_meta", None),
            }
        )
    return results


def get_agent_pending_message_attachments(
    tool_use_context: Any,
) -> List[Attachment]:
    """
    Mirrors getAgentPendingMessageAttachments() in TS. Exported.
    """
    agent_id = getattr(tool_use_context, "agent_id", None)
    if not agent_id:
        return []
    try:
        from claude_code.tasks.local_agent_task.local_agent_task import drain_pending_messages  # type: ignore[import]
        set_app_state = getattr(tool_use_context, "set_app_state_for_tasks", None) or getattr(
            tool_use_context, "set_app_state", None
        )
        drained = drain_pending_messages(agent_id, tool_use_context.get_app_state, set_app_state)
        return [
            {
                "type": "queued_command",
                "prompt": msg,
                "origin": {"kind": "coordinator"},
                "isMeta": True,
            }
            for msg in drained
        ]
    except ImportError:
        return []


async def _build_image_content_blocks(
    pasted_contents: Optional[Any],
) -> List[Dict[str, Any]]:
    if not pasted_contents:
        return []
    try:
        from claude_code.utils.image_resizer import maybe_resize_and_downsample_image_block  # type: ignore[import]
    except ImportError:
        maybe_resize_and_downsample_image_block = None  # type: ignore[assignment]

    image_contents = []
    if isinstance(pasted_contents, dict):
        values = pasted_contents.values()
    elif hasattr(pasted_contents, "values"):
        values = pasted_contents.values()
    else:
        values = pasted_contents

    for item in values:
        if _is_valid_image_paste(item):
            image_contents.append(item)

    if not image_contents:
        return []

    results = []
    for img in image_contents:
        media_type = getattr(img, "media_type", None) or img.get("mediaType") or "image/png"
        content = getattr(img, "content", None) or img.get("content", "")
        image_block: Dict[str, Any] = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": content,
            },
        }
        if maybe_resize_and_downsample_image_block is not None:
            try:
                resized = await maybe_resize_and_downsample_image_block(image_block)
                image_block = resized.get("block", image_block)
            except Exception:
                pass
        results.append(image_block)

    return results


def _is_valid_image_paste(item: Any) -> bool:
    try:
        from claude_code.types.text_input_types import is_valid_image_paste  # type: ignore[import]
        return is_valid_image_paste(item)
    except ImportError:
        media_type = getattr(item, "media_type", None) or (item.get("mediaType") if isinstance(item, dict) else None)
        return bool(media_type and str(media_type).startswith("image/"))


def _get_image_paste_ids(pasted_contents: Optional[Any]) -> List[int]:
    try:
        from claude_code.types.text_input_types import get_image_paste_ids  # type: ignore[import]
        return get_image_paste_ids(pasted_contents)
    except ImportError:
        return []


def _extract_text_content(value: Any) -> str:
    try:
        from claude_code.utils.messages import extract_text_content  # type: ignore[import]
        return extract_text_content(value, "\n")
    except ImportError:
        if isinstance(value, list):
            return "\n".join(
                b.get("text", "") for b in value if isinstance(b, dict) and b.get("type") == "text"
            )
        return str(value)


# ---------------------------------------------------------------------------
# File attachment generation
# ---------------------------------------------------------------------------


async def try_get_pdf_reference(
    filename: str,
) -> Optional[PDFReferenceAttachment]:
    """
    Return a PDFReferenceAttachment for large PDFs, else None.
    Mirrors tryGetPDFReference() in TS. Exported.
    """
    try:
        from claude_code.utils.pdf_utils import is_pdf_extension  # type: ignore[import]
        from claude_code.constants.api_limits import PDF_AT_MENTION_INLINE_THRESHOLD  # type: ignore[import]
    except ImportError:
        return None

    ext = splitext(filename)[1].lower()
    try:
        if not is_pdf_extension(ext):
            return None
    except Exception:
        return None

    try:
        stats = Path(filename).stat()
        try:
            from claude_code.utils.pdf import get_pdf_page_count  # type: ignore[import]
            page_count = await get_pdf_page_count(filename)
        except ImportError:
            page_count = None

        effective_page_count = page_count if page_count is not None else max(1, stats.st_size // (100 * 1024))
        threshold = PDF_AT_MENTION_INLINE_THRESHOLD if not callable(PDF_AT_MENTION_INLINE_THRESHOLD) else PDF_AT_MENTION_INLINE_THRESHOLD()

        if effective_page_count > threshold:
            return {  # type: ignore[return-value]
                "type": "pdf_reference",
                "filename": filename,
                "pageCount": effective_page_count,
                "fileSize": stats.st_size,
                "displayPath": _relative(_get_cwd(), filename),
            }
    except Exception:
        pass

    return None


async def generate_file_attachment(
    filename: str,
    tool_use_context: Any,
    success_event_name: str,
    error_event_name: str,
    mode: Literal["compact", "at-mention"],
    options: Optional[Dict[str, Any]] = None,
) -> Optional[Union[FileAttachment, CompactFileReferenceAttachment, PDFReferenceAttachment, AlreadyReadFileAttachment]]:
    """
    Generate a file attachment by reading a file with proper validation and truncation.
    Mirrors generateFileAttachment() in TS. Exported.
    """
    opts = options or {}
    offset = opts.get("offset")
    limit_val = opts.get("limit")
    cwd = _get_cwd()

    try:
        app_state = tool_use_context.get_app_state()
        if _is_file_read_denied(filename, app_state.get("toolPermissionContext", {})):
            return None
    except Exception:
        pass

    # Large-file check for at-mention
    if mode == "at-mention":
        try:
            from claude_code.utils.file import is_file_within_read_size_limit  # type: ignore[import]
            from claude_code.tools.file_read_tool.limits import get_default_file_reading_limits  # type: ignore[import]
            limits = get_default_file_reading_limits()
            ext = splitext(filename)[1].lower()
            try:
                from claude_code.utils.pdf_utils import is_pdf_extension  # type: ignore[import]
                is_pdf = is_pdf_extension(ext)
            except ImportError:
                is_pdf = ext == ".pdf"
            if not is_file_within_read_size_limit(filename, limits.get("maxSizeBytes", 5 * 1024 * 1024)) and not is_pdf:
                return None
        except ImportError:
            pass

    # Large PDF reference
    if mode == "at-mention":
        pdf_ref = await try_get_pdf_reference(filename)
        if pdf_ref:
            return pdf_ref

    # Already-in-context check
    read_file_state: Any = getattr(tool_use_context, "read_file_state", None)
    if read_file_state is not None and mode == "at-mention":
        try:
            existing = read_file_state.get(filename) if hasattr(read_file_state, "get") else None
            if existing:
                try:
                    from claude_code.utils.file import get_file_modification_time_async  # type: ignore[import]
                    mtime_ms = await get_file_modification_time_async(filename)
                    if existing.get("timestamp", 0) <= mtime_ms and mtime_ms == existing.get("timestamp", -1):
                        return {  # type: ignore[return-value]
                            "type": "already_read_file",
                            "filename": filename,
                            "displayPath": _relative(cwd, filename),
                            "content": {
                                "type": "text",
                                "file": {
                                    "filePath": filename,
                                    "content": existing["content"],
                                    "numLines": count_char_in_string(existing["content"], "\n") + 1,
                                    "startLine": offset or 1,
                                    "totalLines": count_char_in_string(existing["content"], "\n") + 1,
                                },
                            },
                        }
                except ImportError:
                    pass
        except Exception:
            pass

    # Read the file
    try:
        from claude_code.tools.file_read_tool import FileReadTool  # type: ignore[import]
        file_input = {"file_path": filename, "offset": offset, "limit": limit_val}
        is_valid = await FileReadTool.validate_input(file_input, tool_use_context)
        if not is_valid.get("result", True) is False and not is_valid:
            return None
        result = await FileReadTool.call(file_input, tool_use_context)
        return {  # type: ignore[return-value]
            "type": "file",
            "filename": filename,
            "content": result.get("data", result),
            "displayPath": _relative(cwd, filename),
        }
    except ImportError:
        # FileReadTool not ported — fall back to raw read
        try:
            content = Path(filename).read_text(errors="replace")
            return {  # type: ignore[return-value]
                "type": "file",
                "filename": filename,
                "content": {
                    "type": "text",
                    "file": {
                        "filePath": filename,
                        "content": content,
                        "numLines": content.count("\n") + 1,
                        "startLine": offset or 1,
                        "totalLines": content.count("\n") + 1,
                    },
                },
                "displayPath": _relative(cwd, filename),
            }
        except Exception:
            return None
    except Exception:
        # Handle compact_file_reference for mode=compact
        if mode == "compact":
            return {  # type: ignore[return-value]
                "type": "compact_file_reference",
                "filename": filename,
                "displayPath": _relative(cwd, filename),
            }
        return None


# ---------------------------------------------------------------------------
# Changed files
# ---------------------------------------------------------------------------


async def get_changed_files(
    tool_use_context: Any,
) -> List[Attachment]:
    """
    Detect files in readFileState that have been modified since last read.
    Mirrors getChangedFiles() in TS. Exported.
    """
    read_file_state: Any = getattr(tool_use_context, "read_file_state", None)
    if read_file_state is None:
        return []

    try:
        from claude_code.utils.file_state_cache import cache_keys  # type: ignore[import]
        file_paths = cache_keys(read_file_state)
    except ImportError:
        try:
            file_paths = list(read_file_state.keys())
        except Exception:
            return []

    if not file_paths:
        return []

    app_state = getattr(tool_use_context, "get_app_state", lambda: {})()
    results = []

    for file_path in file_paths:
        try:
            file_state = read_file_state.get(file_path)
            if not file_state:
                continue
            if file_state.get("offset") is not None or file_state.get("limit") is not None:
                continue

            try:
                from claude_code.utils.path import expand_path  # type: ignore[import]
                normalized = expand_path(file_path)
            except ImportError:
                normalized = abspath(file_path)

            if _is_file_read_denied(normalized, app_state.get("toolPermissionContext", {})):
                continue

            try:
                from claude_code.utils.file import get_file_modification_time_async  # type: ignore[import]
                mtime = await get_file_modification_time_async(normalized)
            except ImportError:
                mtime = int(Path(normalized).stat().st_mtime_ns // 1_000_000)

            if mtime <= file_state.get("timestamp", 0):
                continue

            attachment = await generate_file_attachment(
                normalized,
                tool_use_context,
                "tengu_changed_file_success",
                "tengu_changed_file_error",
                "at-mention",
            )
            if attachment:
                results.append(attachment)

        except FileNotFoundError:
            try:
                read_file_state.delete(file_path)
            except Exception:
                pass
        except Exception:
            pass

    return results


# ---------------------------------------------------------------------------
# Nested memory attachments
# ---------------------------------------------------------------------------


async def _get_nested_memory_attachments(
    tool_use_context: Any,
) -> List[Attachment]:
    triggers: Any = getattr(tool_use_context, "nested_memory_attachment_triggers", None)
    if not triggers or len(triggers) == 0:
        return []

    app_state = tool_use_context.get_app_state()
    attachments: List[Attachment] = []

    for file_path in list(triggers):
        try:
            nested = await _get_nested_memory_attachments_for_file(
                file_path, tool_use_context, app_state
            )
            attachments.extend(nested)
        except Exception:
            pass

    triggers.clear()
    return attachments


async def _get_nested_memory_attachments_for_file(
    file_path: str,
    tool_use_context: Any,
    app_state: Any,
) -> List[Attachment]:
    attachments: List[Attachment] = []
    try:
        permission_context = app_state.get("toolPermissionContext", {})
        try:
            from claude_code.utils.permissions.filesystem import path_in_allowed_working_path  # type: ignore[import]
            if not path_in_allowed_working_path(file_path, permission_context):
                return attachments
        except ImportError:
            pass

        from claude_code.utils.claudemd import (  # type: ignore[import]
            get_managed_and_user_conditional_rules,
            get_memory_files_for_nested_directory,
            get_conditional_rules_for_cwd_level_directory,
        )

        processed_paths: Set[str] = set()
        original_cwd = _get_original_cwd()

        # Phase 1: Managed and User conditional rules
        managed_user_rules = await get_managed_and_user_conditional_rules(file_path, processed_paths)
        attachments.extend(memory_files_to_attachments(managed_user_rules, tool_use_context, file_path))

        # Phase 2: Get directories
        dirs = get_directories_to_process(file_path, original_cwd)

        # Phase 3: Nested directories
        for d in dirs["nestedDirs"]:
            memory_files = await get_memory_files_for_nested_directory(d, file_path, processed_paths)
            attachments.extend(memory_files_to_attachments(memory_files, tool_use_context, file_path))

        # Phase 4: CWD-level directories (conditional rules only)
        for d in dirs["cwdLevelDirs"]:
            conditional_rules = await get_conditional_rules_for_cwd_level_directory(d, file_path, processed_paths)
            attachments.extend(memory_files_to_attachments(conditional_rules, tool_use_context, file_path))

    except ImportError:
        pass
    except Exception:
        pass

    return attachments


# ---------------------------------------------------------------------------
# Dynamic skill attachments
# ---------------------------------------------------------------------------


async def _get_dynamic_skill_attachments(
    tool_use_context: Any,
) -> List[Attachment]:
    attachments: List[Attachment] = []
    triggers: Any = getattr(tool_use_context, "dynamic_skill_dir_triggers", None)
    if not triggers or len(triggers) == 0:
        return attachments

    cwd = _get_cwd()

    import asyncio
    import os as _os

    async def _check_dir(skill_dir: str) -> Dict[str, Any]:
        try:
            entries = _os.scandir(skill_dir)
            candidates = [e.name for e in entries if e.is_dir() or e.is_symlink()]
        except Exception:
            return {"skillDir": skill_dir, "skillNames": []}

        skill_names = []
        for name in candidates:
            skill_md = Path(skill_dir) / name / "SKILL.md"
            if skill_md.exists():
                skill_names.append(name)

        return {"skillDir": skill_dir, "skillNames": skill_names}

    results = await asyncio.gather(*[_check_dir(d) for d in list(triggers)])
    for item in results:
        if item["skillNames"]:
            attachments.append(
                {
                    "type": "dynamic_skill",
                    "skillDir": item["skillDir"],
                    "skillNames": item["skillNames"],
                    "displayPath": _relative(cwd, item["skillDir"]),
                }
            )

    triggers.clear()
    return attachments


# ---------------------------------------------------------------------------
# IDE-related attachments
# ---------------------------------------------------------------------------


async def _get_selected_lines_from_ide(
    ide_selection: Optional[Any],
    tool_use_context: Any,
) -> List[Attachment]:
    try:
        from claude_code.utils.ide import get_connected_ide_name  # type: ignore[import]
        ide_name = get_connected_ide_name(tool_use_context.options.mcp_clients)
    except ImportError:
        return []

    if (
        not ide_name
        or not ide_selection
        or getattr(ide_selection, "line_start", None) is None
        or not getattr(ide_selection, "text", None)
        or not getattr(ide_selection, "file_path", None)
    ):
        return []

    try:
        app_state = tool_use_context.get_app_state()
        if _is_file_read_denied(ide_selection.file_path, app_state.get("toolPermissionContext", {})):
            return []
    except Exception:
        pass

    cwd = _get_cwd()
    return [
        {
            "type": "selected_lines_in_ide",
            "ideName": ide_name,
            "lineStart": ide_selection.line_start,
            "lineEnd": ide_selection.line_start + getattr(ide_selection, "line_count", 1) - 1,
            "filename": ide_selection.file_path,
            "content": ide_selection.text,
            "displayPath": _relative(cwd, ide_selection.file_path),
        }
    ]


async def _get_opened_file_from_ide(
    ide_selection: Optional[Any],
    tool_use_context: Any,
) -> List[Attachment]:
    if not ide_selection or not getattr(ide_selection, "file_path", None) or getattr(ide_selection, "text", None):
        return []

    try:
        app_state = tool_use_context.get_app_state()
        if _is_file_read_denied(ide_selection.file_path, app_state.get("toolPermissionContext", {})):
            return []
    except Exception:
        pass

    nested = await _get_nested_memory_attachments_for_file(
        ide_selection.file_path, tool_use_context, {}
    )
    return [
        *nested,
        {"type": "opened_file_in_ide", "filename": ide_selection.file_path},
    ]


# ---------------------------------------------------------------------------
# At-mentioned files processing
# ---------------------------------------------------------------------------


async def _process_at_mentioned_files(
    input_text: str,
    tool_use_context: Any,
) -> List[Attachment]:
    files = extract_at_mentioned_files(input_text)
    if not files:
        return []

    cwd = _get_cwd()
    app_state = tool_use_context.get_app_state()

    async def _process_one(file: str) -> Optional[Attachment]:
        try:
            parsed = parse_at_mentioned_file_lines(file)
            filename_raw = parsed["filename"]

            try:
                from claude_code.utils.path import expand_path  # type: ignore[import]
                absolute_filename = expand_path(filename_raw)
            except ImportError:
                absolute_filename = abspath(filename_raw)

            if _is_file_read_denied(absolute_filename, app_state.get("toolPermissionContext", {})):
                return None

            # Directory?
            p = Path(absolute_filename)
            if p.is_dir():
                MAX_DIR_ENTRIES = 1000
                entries = sorted(p.iterdir(), key=lambda x: x.name)
                truncated = len(entries) > MAX_DIR_ENTRIES
                names = [e.name for e in entries[:MAX_DIR_ENTRIES]]
                if truncated:
                    names.append(f"… and {len(entries) - MAX_DIR_ENTRIES} more entries")
                return {
                    "type": "directory",
                    "path": absolute_filename,
                    "content": "\n".join(names),
                    "displayPath": _relative(cwd, absolute_filename),
                }

            return await generate_file_attachment(
                absolute_filename,
                tool_use_context,
                "tengu_at_mention_extracting_filename_success",
                "tengu_at_mention_extracting_filename_error",
                "at-mention",
                {
                    "offset": parsed.get("lineStart"),
                    "limit": (
                        parsed["lineEnd"] - parsed["lineStart"] + 1
                        if parsed.get("lineEnd") is not None and parsed.get("lineStart") is not None
                        else None
                    ),
                },
            )
        except Exception:
            return None

    import asyncio
    results = await asyncio.gather(*[_process_one(f) for f in files])
    return [r for r in results if r is not None]


def _process_agent_mentions(
    input_text: str,
    agents: List[Any],
) -> List[Attachment]:
    agent_mentions = extract_agent_mentions(input_text)
    if not agent_mentions:
        return []

    results: List[Attachment] = []
    for mention in agent_mentions:
        agent_type = mention.replace("agent-", "")
        agent_def = next((a for a in agents if getattr(a, "agent_type", None) == agent_type), None)
        if not agent_def:
            continue
        results.append({"type": "agent_mention", "agentType": agent_def.agent_type})

    return results


async def _process_mcp_resource_attachments(
    input_text: str,
    tool_use_context: Any,
) -> List[Attachment]:
    resource_mentions = extract_mcp_resource_mentions(input_text)
    if not resource_mentions:
        return []

    mcp_clients = getattr(tool_use_context.options, "mcp_clients", []) or []

    async def _process_one(mention: str) -> Optional[Attachment]:
        try:
            colon_idx = mention.index(":")
            server_name = mention[:colon_idx]
            uri = mention[colon_idx + 1:]
            if not server_name or not uri:
                return None

            client = next((c for c in mcp_clients if getattr(c, "name", None) == server_name), None)
            if not client or getattr(client, "type", None) != "connected":
                return None

            mcp_resources = (getattr(tool_use_context.options, "mcp_resources", {}) or {}).get(server_name, [])
            resource_info = next((r for r in mcp_resources if getattr(r, "uri", None) == uri), None)
            if not resource_info:
                return None

            result = await client.client.read_resource({"uri": uri})
            return {
                "type": "mcp_resource",
                "server": server_name,
                "uri": uri,
                "name": getattr(resource_info, "name", uri) or uri,
                "description": getattr(resource_info, "description", None),
                "content": result,
            }
        except Exception:
            return None

    import asyncio
    results = await asyncio.gather(*[_process_one(m) for m in resource_mentions])
    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Diagnostic attachments
# ---------------------------------------------------------------------------


async def _get_diagnostic_attachments(
    tool_use_context: Any,
) -> List[Attachment]:
    try:
        from claude_code.tools.bash_tool.tool_name import BASH_TOOL_NAME  # type: ignore[import]
        from claude_code.tool import tool_matches_name  # type: ignore[import]
        if not any(tool_matches_name(t, BASH_TOOL_NAME) for t in (tool_use_context.options.tools or [])):
            return []
    except ImportError:
        pass

    try:
        from claude_code.services.diagnostic_tracking import diagnostic_tracker  # type: ignore[import]
        new_diagnostics = await diagnostic_tracker.get_new_diagnostics()
        if not new_diagnostics:
            return []
        return [{"type": "diagnostics", "files": new_diagnostics, "isNew": True}]
    except ImportError:
        return []


async def _get_lsp_diagnostic_attachments(
    tool_use_context: Any,
) -> List[Attachment]:
    try:
        from claude_code.tools.bash_tool.tool_name import BASH_TOOL_NAME  # type: ignore[import]
        from claude_code.tool import tool_matches_name  # type: ignore[import]
        if not any(tool_matches_name(t, BASH_TOOL_NAME) for t in (tool_use_context.options.tools or [])):
            return []
    except ImportError:
        pass

    try:
        from claude_code.services.lsp.lsp_diagnostic_registry import (  # type: ignore[import]
            check_for_lsp_diagnostics,
            clear_all_lsp_diagnostics,
        )
        diagnostic_sets = check_for_lsp_diagnostics()
        if not diagnostic_sets:
            return []
        attachments = [
            {"type": "diagnostics", "files": ds["files"], "isNew": True}
            for ds in diagnostic_sets
        ]
        clear_all_lsp_diagnostics()
        return attachments
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Todo / task reminder attachments
# ---------------------------------------------------------------------------


def _get_todo_reminder_turn_counts(
    messages: List[Dict[str, Any]],
) -> Dict[str, int]:
    last_todo_write_index = -1
    last_reminder_index = -1
    turns_since_write = 0
    turns_since_reminder = 0

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("type") == "assistant":
            if _is_thinking_message(msg):
                continue
            content = msg.get("message", {}).get("content", [])
            if (
                last_todo_write_index == -1
                and isinstance(content, list)
                and any(
                    isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "TodoWrite"
                    for b in content
                )
            ):
                last_todo_write_index = i
            if last_todo_write_index == -1:
                turns_since_write += 1
            if last_reminder_index == -1:
                turns_since_reminder += 1
        elif (
            last_reminder_index == -1
            and msg.get("type") == "attachment"
            and msg.get("attachment", {}).get("type") == "todo_reminder"
        ):
            last_reminder_index = i

        if last_todo_write_index != -1 and last_reminder_index != -1:
            break

    return {
        "turnsSinceLastTodoWrite": turns_since_write,
        "turnsSinceLastReminder": turns_since_reminder,
    }


async def _get_todo_reminder_attachments(
    messages: Optional[List[Dict[str, Any]]],
    tool_use_context: Any,
) -> List[Attachment]:
    try:
        from claude_code.tools.todo_write_tool.constants import TODO_WRITE_TOOL_NAME  # type: ignore[import]
        from claude_code.tool import tool_matches_name  # type: ignore[import]
        if not any(tool_matches_name(t, TODO_WRITE_TOOL_NAME) for t in (tool_use_context.options.tools or [])):
            return []
    except ImportError:
        return []

    if not messages:
        return []

    counts = _get_todo_reminder_turn_counts(messages)
    if (
        counts["turnsSinceLastTodoWrite"] >= TODO_REMINDER_CONFIG["TURNS_SINCE_WRITE"]
        and counts["turnsSinceLastReminder"] >= TODO_REMINDER_CONFIG["TURNS_BETWEEN_REMINDERS"]
    ):
        try:
            agent_key = getattr(tool_use_context, "agent_id", None) or _get_session_id()
            app_state = tool_use_context.get_app_state()
            todos = app_state.get("todos", {}).get(agent_key, [])
            return [{"type": "todo_reminder", "content": todos, "itemCount": len(todos)}]
        except Exception:
            return []

    return []


def _get_task_reminder_turn_counts(
    messages: List[Dict[str, Any]],
) -> Dict[str, int]:
    try:
        from claude_code.tools.task_create_tool.constants import TASK_CREATE_TOOL_NAME  # type: ignore[import]
        from claude_code.tools.task_update_tool.constants import TASK_UPDATE_TOOL_NAME  # type: ignore[import]
        task_tool_names = {TASK_CREATE_TOOL_NAME, TASK_UPDATE_TOOL_NAME}
    except ImportError:
        task_tool_names = {"TaskCreate", "TaskUpdate"}

    last_task_mgmt_index = -1
    last_reminder_index = -1
    turns_since_task = 0
    turns_since_reminder = 0

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if msg.get("type") == "assistant":
            if _is_thinking_message(msg):
                continue
            content = msg.get("message", {}).get("content", [])
            if (
                last_task_mgmt_index == -1
                and isinstance(content, list)
                and any(
                    isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") in task_tool_names
                    for b in content
                )
            ):
                last_task_mgmt_index = i
            if last_task_mgmt_index == -1:
                turns_since_task += 1
            if last_reminder_index == -1:
                turns_since_reminder += 1
        elif (
            last_reminder_index == -1
            and msg.get("type") == "attachment"
            and msg.get("attachment", {}).get("type") == "task_reminder"
        ):
            last_reminder_index = i

        if last_task_mgmt_index != -1 and last_reminder_index != -1:
            break

    return {
        "turnsSinceLastTaskManagement": turns_since_task,
        "turnsSinceLastReminder": turns_since_reminder,
    }


async def _get_task_reminder_attachments(
    messages: Optional[List[Dict[str, Any]]],
    tool_use_context: Any,
) -> List[Attachment]:
    if os.environ.get("USER_TYPE") == "ant":
        return []

    try:
        from claude_code.utils.tasks import is_todo_v2_enabled, list_tasks, get_task_list_id  # type: ignore[import]
        if not is_todo_v2_enabled():
            return []
    except ImportError:
        return []

    try:
        from claude_code.tools.task_update_tool.constants import TASK_UPDATE_TOOL_NAME  # type: ignore[import]
        from claude_code.tool import tool_matches_name  # type: ignore[import]
        if not any(tool_matches_name(t, TASK_UPDATE_TOOL_NAME) for t in (tool_use_context.options.tools or [])):
            return []
    except ImportError:
        return []

    if not messages:
        return []

    counts = _get_task_reminder_turn_counts(messages)
    if (
        counts["turnsSinceLastTaskManagement"] >= TODO_REMINDER_CONFIG["TURNS_SINCE_WRITE"]
        and counts["turnsSinceLastReminder"] >= TODO_REMINDER_CONFIG["TURNS_BETWEEN_REMINDERS"]
    ):
        try:
            tasks = await list_tasks(get_task_list_id())
            return [{"type": "task_reminder", "content": tasks, "itemCount": len(tasks)}]
        except Exception:
            return []

    return []


async def _get_unified_task_attachments(
    tool_use_context: Any,
) -> List[Attachment]:
    try:
        from claude_code.utils.task.framework import generate_task_attachments, apply_task_offsets_and_evictions  # type: ignore[import]
        from claude_code.utils.task.disk_output import get_task_output_path  # type: ignore[import]
        app_state = tool_use_context.get_app_state()
        result = await generate_task_attachments(app_state)
        apply_task_offsets_and_evictions(
            tool_use_context.set_app_state,
            result["updatedTaskOffsets"],
            result["evictedTaskIds"],
        )
        return [
            {
                "type": "task_status",
                "taskId": ta["taskId"],
                "taskType": ta["taskType"],
                "status": ta["status"],
                "description": ta["description"],
                "deltaSummary": ta["deltaSummary"],
                "outputFilePath": get_task_output_path(ta["taskId"]),
            }
            for ta in result["attachments"]
        ]
    except ImportError:
        return []


async def _get_async_hook_response_attachments() -> List[Attachment]:
    try:
        from claude_code.utils.hooks.async_hook_registry import (  # type: ignore[import]
            check_for_async_hook_responses,
            remove_delivered_async_hooks,
        )
        responses = await check_for_async_hook_responses()
        if not responses:
            return []

        attachments = [
            {
                "type": "async_hook_response",
                "processId": r["processId"],
                "hookName": r["hookName"],
                "hookEvent": r["hookEvent"],
                "toolName": r.get("toolName"),
                "response": r["response"],
                "stdout": r["stdout"],
                "stderr": r["stderr"],
                "exitCode": r.get("exitCode"),
            }
            for r in responses
        ]
        if responses:
            remove_delivered_async_hooks([r["processId"] for r in responses])

        return attachments
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Teammate mailbox / team context
# ---------------------------------------------------------------------------


async def _get_teammate_mailbox_attachments(
    tool_use_context: Any,
) -> List[Attachment]:
    # Guarded behind agent swarms enabled check
    try:
        from claude_code.utils.agent_swarms_enabled import is_agent_swarms_enabled  # type: ignore[import]
        if not is_agent_swarms_enabled():
            return []
    except ImportError:
        return []

    if os.environ.get("USER_TYPE") != "ant":
        return []

    try:
        from claude_code.utils.teammate_mailbox import (  # type: ignore[import]
            read_unread_messages,
            mark_messages_as_read_by_predicate,
            is_structured_protocol_message,
            is_idle_notification,
        )
        from claude_code.utils.teammate import get_agent_name, get_team_name, is_team_lead  # type: ignore[import]

        app_state = tool_use_context.get_app_state()
        team_name = get_team_name(app_state.get("teamContext"))
        agent_name = get_agent_name()
        team_lead_status = is_team_lead(app_state.get("teamContext"))

        if not agent_name and team_lead_status and app_state.get("teamContext"):
            lead_id = app_state["teamContext"].get("leadAgentId")
            agent_name = app_state["teamContext"].get("teammates", {}).get(lead_id, {}).get("name", "team-lead")

        if not agent_name:
            return []

        all_unread = await read_unread_messages(agent_name, team_name)
        unread = [m for m in all_unread if not is_structured_protocol_message(m["text"])]

        # Collapse duplicate idle notifications
        idle_by_index: Dict[int, str] = {}
        latest_idle_by_agent: Dict[str, int] = {}
        all_messages = list(unread)
        for i, m in enumerate(all_messages):
            idle = is_idle_notification(m["text"])
            if idle:
                idle_by_index[i] = idle["from"]
                latest_idle_by_agent[idle["from"]] = i

        if len(idle_by_index) > len(latest_idle_by_agent):
            all_messages = [
                m for i, m in enumerate(all_messages)
                if i not in idle_by_index or latest_idle_by_agent.get(idle_by_index[i]) == i
            ]

        if not all_messages:
            return []

        attachment: List[Attachment] = [
            {
                "type": "teammate_mailbox",
                "messages": [
                    {
                        "from": m.get("from", ""),
                        "text": m.get("text", ""),
                        "timestamp": m.get("timestamp", ""),
                        "color": m.get("color"),
                        "summary": m.get("summary"),
                    }
                    for m in all_messages
                ],
            }
        ]

        if unread:
            await mark_messages_as_read_by_predicate(
                agent_name,
                lambda m: not is_structured_protocol_message(m["text"]),
                team_name,
            )

        return attachment
    except ImportError:
        return []
    except Exception:
        return []


def _get_team_context_attachment(
    messages: List[Dict[str, Any]],
) -> List[Attachment]:
    try:
        from claude_code.utils.teammate import get_agent_name, get_team_name, get_agent_id  # type: ignore[import]
        from claude_code.utils.env_utils import get_claude_config_home_dir  # type: ignore[import]
        team_name = get_team_name()
        agent_id = get_agent_id()
        agent_name = get_agent_name()
    except ImportError:
        return []

    if not team_name or not agent_id:
        return []

    has_assistant = any(m.get("type") == "assistant" for m in messages)
    if has_assistant:
        return []

    try:
        config_dir = get_claude_config_home_dir()
    except Exception:
        config_dir = os.path.expanduser("~/.claude")

    return [
        {
            "type": "team_context",
            "agentId": agent_id,
            "agentName": agent_name or agent_id,
            "teamName": team_name,
            "teamConfigPath": f"{config_dir}/teams/{team_name}/config.json",
            "taskListPath": f"{config_dir}/tasks/{team_name}/",
        }
    ]


# ---------------------------------------------------------------------------
# Permission / file-read deny check
# ---------------------------------------------------------------------------


def _is_file_read_denied(
    file_path: str,
    tool_permission_context: Any,
) -> bool:
    try:
        from claude_code.utils.permissions.filesystem import matching_rule_for_input  # type: ignore[import]
        rule = matching_rule_for_input(file_path, tool_permission_context, "read", "deny")
        return rule is not None
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Attachment message factory
# ---------------------------------------------------------------------------


def create_attachment_message(attachment: Attachment) -> AttachmentMessage:
    """
    Wrap an Attachment in an AttachmentMessage with UUID + timestamp.
    Mirrors createAttachmentMessage() in TS. Exported.
    """
    return {
        "attachment": attachment,
        "type": "attachment",
        "uuid": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ---------------------------------------------------------------------------
# maybe() helper — run a getter, log errors, return [] on failure
# ---------------------------------------------------------------------------


import random
import time


async def _maybe(label: str, f: Any) -> List[Any]:
    """
    Safe wrapper: run f(), swallow errors, return [].
    Mirrors maybe() in TS.
    """
    start = time.monotonic()
    try:
        result = await f()
        return result if result is not None else []
    except Exception as e:
        import logging
        logging.getLogger(__name__).debug("Attachment error in %s: %s", label, e)
        return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


async def get_attachments(
    input_text: Optional[str],
    tool_use_context: Any,
    ide_selection: Optional[Any] = None,
    queued_commands: Optional[List[Any]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    query_source: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> List[Attachment]:
    """
    Main attachment collection entry point.
    Mirrors getAttachments() in TS.
    """
    import asyncio

    if is_env_truthy(os.environ.get("CLAUDE_CODE_DISABLE_ATTACHMENTS")) or is_env_truthy(
        os.environ.get("CLAUDE_CODE_SIMPLE")
    ):
        return await get_queued_command_attachments(queued_commands)

    opts = options or {}
    skip_skill_discovery = opts.get("skipSkillDiscovery", False)
    is_main_thread = not getattr(tool_use_context, "agent_id", None)

    # User-input attachments (requires input)
    if input_text:
        user_input_attachments = await asyncio.gather(
            _maybe("at_mentioned_files", lambda: _process_at_mentioned_files(input_text, tool_use_context)),
            _maybe("mcp_resources", lambda: _process_mcp_resource_attachments(input_text, tool_use_context)),
            _maybe("agent_mentions", lambda: asyncio.coroutine(lambda: _process_agent_mentions(
                input_text,
                getattr(tool_use_context.options, "agent_definitions", None) and
                tool_use_context.options.agent_definitions.active_agents or [],
            ))()),
        )
    else:
        user_input_attachments = [[], [], []]

    # Thread-safe attachments
    all_thread_futs = [
        _maybe("queued_commands", lambda: get_queued_command_attachments(queued_commands)),
        _maybe("date_change", lambda: asyncio.coroutine(lambda: get_date_change_attachments(messages))()),
        _maybe("ultrathink_effort", lambda: asyncio.coroutine(lambda: _get_ultrathink_effort_attachment(input_text))()),
        _maybe("deferred_tools_delta", lambda: asyncio.coroutine(lambda: get_deferred_tools_delta_attachment(
            getattr(tool_use_context.options, "tools", []),
            getattr(tool_use_context.options, "main_loop_model", ""),
            messages,
            None,
        ))()),
        _maybe("agent_listing_delta", lambda: asyncio.coroutine(lambda: get_agent_listing_delta_attachment(tool_use_context, messages))()),
        _maybe("mcp_instructions_delta", lambda: asyncio.coroutine(lambda: get_mcp_instructions_delta_attachment(
            getattr(tool_use_context.options, "mcp_clients", []),
            getattr(tool_use_context.options, "tools", []),
            getattr(tool_use_context.options, "main_loop_model", ""),
            messages,
        ))()),
        _maybe("changed_files", lambda: get_changed_files(tool_use_context)),
        _maybe("nested_memory", lambda: _get_nested_memory_attachments(tool_use_context)),
        _maybe("dynamic_skill", lambda: _get_dynamic_skill_attachments(tool_use_context)),
        _maybe("skill_listing", lambda: _get_skill_listing_attachments(tool_use_context)),
        _maybe("plan_mode", lambda: _get_plan_mode_attachments(messages, tool_use_context)),
        _maybe("plan_mode_exit", lambda: _get_plan_mode_exit_attachment(tool_use_context)),
        _maybe("auto_mode", lambda: _get_auto_mode_attachments(messages, tool_use_context)),
        _maybe("auto_mode_exit", lambda: _get_auto_mode_exit_attachment(tool_use_context)),
        _maybe("todo_reminders", lambda: _get_todo_or_task_reminder_attachments(messages, tool_use_context)),
        _maybe("agent_pending_messages", lambda: asyncio.coroutine(lambda: get_agent_pending_message_attachments(tool_use_context))()),
        _maybe("critical_system_reminder", lambda: asyncio.coroutine(lambda: _get_critical_system_reminder_attachment(tool_use_context))()),
    ]

    # Main thread-only attachments
    main_thread_futs = []
    if is_main_thread:
        main_thread_futs = [
            _maybe("ide_selection", lambda: _get_selected_lines_from_ide(ide_selection, tool_use_context)),
            _maybe("ide_opened_file", lambda: _get_opened_file_from_ide(ide_selection, tool_use_context)),
            _maybe("output_style", lambda: asyncio.coroutine(lambda: _get_output_style_attachment())()),
            _maybe("diagnostics", lambda: _get_diagnostic_attachments(tool_use_context)),
            _maybe("lsp_diagnostics", lambda: _get_lsp_diagnostic_attachments(tool_use_context)),
            _maybe("unified_tasks", lambda: _get_unified_task_attachments(tool_use_context)),
            _maybe("async_hook_responses", lambda: _get_async_hook_response_attachments()),
            _maybe("token_usage", lambda: asyncio.coroutine(lambda: _get_token_usage_attachment(messages or [], getattr(tool_use_context.options, "main_loop_model", "")))()),
            _maybe("budget_usd", lambda: asyncio.coroutine(lambda: _get_max_budget_usd_attachment(getattr(tool_use_context.options, "max_budget_usd", None)))()),
            _maybe("output_token_usage", lambda: asyncio.coroutine(lambda: _get_output_token_usage_attachment())()),
            _maybe("verify_plan_reminder", lambda: _get_verify_plan_reminder_attachment(messages, tool_use_context)),
        ]

    thread_results, main_results = await asyncio.gather(
        asyncio.gather(*all_thread_futs),
        asyncio.gather(*main_thread_futs),
    )

    all_attachments: List[Attachment] = []
    for group in user_input_attachments:
        if isinstance(group, list):
            all_attachments.extend(group)
    for group in list(thread_results) + list(main_results):
        if isinstance(group, list):
            all_attachments.extend(group)

    return [a for a in all_attachments if a is not None]


async def _get_todo_or_task_reminder_attachments(
    messages: Optional[List[Dict[str, Any]]],
    tool_use_context: Any,
) -> List[Attachment]:
    try:
        from claude_code.utils.tasks import is_todo_v2_enabled  # type: ignore[import]
        if is_todo_v2_enabled():
            return await _get_task_reminder_attachments(messages, tool_use_context)
    except ImportError:
        pass
    return await _get_todo_reminder_attachments(messages, tool_use_context)


async def get_attachment_messages(
    input_text: Optional[str],
    tool_use_context: Any,
    ide_selection: Optional[Any] = None,
    queued_commands: Optional[List[Any]] = None,
    messages: Optional[List[Dict[str, Any]]] = None,
    query_source: Optional[str] = None,
    options: Optional[Dict[str, Any]] = None,
) -> AsyncGenerator[AttachmentMessage, None]:
    """
    Async generator of AttachmentMessage objects.
    Mirrors getAttachmentMessages() in TS. Exported.
    """
    attachments = await get_attachments(
        input_text,
        tool_use_context,
        ide_selection,
        queued_commands,
        messages,
        query_source,
        options,
    )

    for attachment in attachments:
        yield create_attachment_message(attachment)


# ---------------------------------------------------------------------------
# Legacy / simple API (from original stub — preserved for compatibility)
# ---------------------------------------------------------------------------

import base64
import mimetypes

SUPPORTED_IMAGE_TYPES: Set[str] = {"image/jpeg", "image/png", "image/gif", "image/webp"}
MAX_IMAGE_SIZE: int = 5 * 1024 * 1024  # 5MB


def file_to_base64(path: Union[str, Path]) -> str:
    """Encode a local file as base64 string."""
    return base64.standard_b64encode(Path(path).read_bytes()).decode()


def image_block_from_file(path: Union[str, Path]) -> Dict[str, Any]:
    """Convert a local image file to an Anthropic image content block."""
    p = Path(path)
    mime = mimetypes.guess_type(str(p))[0] or "image/jpeg"
    if mime not in SUPPORTED_IMAGE_TYPES:
        raise ValueError(f"Unsupported image type: {mime}")
    data = file_to_base64(p)
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": mime, "data": data},
    }


def image_block_from_url(url: str) -> Dict[str, Any]:
    """Return an Anthropic image content block referencing a URL."""
    return {"type": "image", "source": {"type": "url", "url": url}}


def text_file_block(
    path: Union[str, Path], label: Optional[str] = None
) -> Dict[str, Any]:
    """Convert a text file to a text content block with filename annotation."""
    content = Path(path).read_text(errors="replace")
    name = label or Path(path).name
    return {"type": "text", "text": f"[{name}]\n{content}"}


def process_attachments(paths: List[str]) -> List[Dict[str, Any]]:
    """Process a list of file paths into content blocks."""
    blocks = []
    for p in paths:
        mime = mimetypes.guess_type(p)[0] or ""
        if mime in SUPPORTED_IMAGE_TYPES:
            blocks.append(image_block_from_file(p))
        elif mime.startswith("text/") or p.endswith((".md", ".txt", ".py", ".ts", ".js")):
            blocks.append(text_file_block(p))
    return blocks

"""
Tool execution engine.
Ported from services/tools/toolExecution.ts (1745 lines).

This module implements the core tool-use execution pipeline:
  1. Find tool by name (with alias fallback)
  2. Validate input schema (Zod → jsonschema/pydantic equivalent)
  3. Run pre-tool hooks
  4. Permission check (canUseTool / resolveHookPermissionDecision)
  5. Execute tool.call()
  6. Run post-tool hooks
  7. Return list of MessageUpdateLazy results

Progress/streaming is modelled with an asyncio.Queue-backed Stream
similar to the TS Stream<T> utility.
"""
from __future__ import annotations

import asyncio
import os
import time
import uuid as _uuid
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Union,
)

if TYPE_CHECKING:
    from claude_code.tool import Tool, ToolUseContext
    from claude_code.types.permissions import PermissionResult, PermissionDecision

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Minimum total hook duration (ms) to show inline timing summary
HOOK_TIMING_DISPLAY_THRESHOLD_MS = 500

# Log a debug warning when hooks/permission-decision block for this long.
# Matches BashTool's PROGRESS_THRESHOLD_MS — the collapsed view feels stuck past this.
_SLOW_PHASE_LOG_THRESHOLD_MS = 2000

# ---------------------------------------------------------------------------
# Lazy imports for optional module support
# ---------------------------------------------------------------------------

def _get_cancel_message() -> str:
    try:
        from claude_code.utils.messages import CANCEL_MESSAGE
        return CANCEL_MESSAGE
    except ImportError:
        return "Cancelled"


def _sanitize_tool_name(name: str) -> str:
    try:
        from claude_code.utils.analytics_metadata import sanitize_tool_name_for_analytics
        return sanitize_tool_name_for_analytics(name)
    except ImportError:
        # Strip PII: keep alphanumeric + underscore, truncate
        import re
        return re.sub(r"[^a-zA-Z0-9_]", "_", name)[:60]


def _log_event(event_name: str, data: dict) -> None:
    try:
        from claude_code.services.analytics import log_event
        log_event(event_name, data)
    except ImportError:
        pass


def _log_otel_event(event_name: str, data: dict) -> None:
    try:
        from claude_code.utils.telemetry.events import log_otel_event
        asyncio.ensure_future(log_otel_event(event_name, data))
    except Exception:
        pass


def _log_for_debugging(msg: str, opts: Optional[dict] = None) -> None:
    try:
        from claude_code.utils.debug import log_for_debugging
        log_for_debugging(msg, opts)
    except ImportError:
        pass  # Silently skip if debug logging not available


def _log_error(error: Exception) -> None:
    try:
        from claude_code.utils.log import log_error
        log_error(error)
    except ImportError:
        pass


def _is_mcp_tool(tool: Any) -> bool:
    return bool(getattr(tool, "is_mcp", False))


def _get_all_base_tools() -> list:
    try:
        from claude_code.tools import get_all_base_tools
        return get_all_base_tools()
    except ImportError:
        return []


def _find_tool_by_name(tools: list, name: str) -> Optional[Any]:
    try:
        from claude_code.tool import find_tool_by_name
        return find_tool_by_name(tools, name)
    except ImportError:
        for t in tools:
            if getattr(t, "name", None) == name:
                return t
        return None


def _json_stringify(obj: Any) -> str:
    import json
    try:
        return json.dumps(obj, default=str)
    except Exception:
        return str(obj)


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class MessageUpdateContextModifier:
    tool_use_id: str
    modify_context: Callable


@dataclass
class MessageUpdateLazy:
    """
    Mirrors TS: MessageUpdateLazy<M>.
    Wraps a message (UserMessage / ProgressMessage / AttachmentMessage)
    plus an optional context modifier callback.
    """
    message: Any
    context_modifier: Optional[MessageUpdateContextModifier] = None


McpServerType = Optional[str]  # 'stdio' | 'sse' | 'http' | 'ws' | 'sdk' | ...

# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def classify_tool_error(error: Any) -> str:
    """
    Classify a tool execution error into a telemetry-safe string.

    In minified/external builds, error.constructor.name is mangled — this
    extracts structured, telemetry-safe information instead:
    - TelemetrySafeError: use its telemetry_message (already vetted)
    - OSError / IOError: log the errno code (ENOENT, EACCES, etc.)
    - Known error types: use their unmangled name
    - Fallback: "Error"
    """
    try:
        from claude_code.utils.errors import TelemetrySafeError
        if isinstance(error, TelemetrySafeError):
            return error.telemetry_message[:200]
    except ImportError:
        pass

    if isinstance(error, OSError):
        # Python OSError.strerror is analogous to Node errno code
        code = getattr(error, "errno", None)
        if code is not None:
            import errno as _errno
            name = _errno.errorcode.get(code, str(code))
            return f"Error:{name}"

    if isinstance(error, Exception):
        name = type(error).__name__
        # Protect against mangled names (very short = likely minified / bad)
        if name and name != "Exception" and len(name) > 3:
            return name[:60]
        return "Error"

    return "UnknownError"


# ---------------------------------------------------------------------------
# OTel source helpers (mirror TS ruleSourceToOTelSource / decisionReasonToOTelSource)
# ---------------------------------------------------------------------------

def _rule_source_to_otel_source(rule_source: str, behavior: str) -> str:
    """
    Map a rule's origin to the documented OTel `source` vocabulary:
    session-scoped grants → temporary, on-disk grants → permanent,
    user-authored denies → user_reject, everything else → config.
    """
    if rule_source in ("session",):
        return "user_temporary" if behavior == "allow" else "user_reject"
    if rule_source in ("localSettings", "userSettings"):
        return "user_permanent" if behavior == "allow" else "user_reject"
    return "config"


def _decision_reason_to_otel_source(reason: Any, behavior: str) -> str:
    """
    Map a PermissionDecisionReason to the OTel `source` label for the
    non-interactive tool_decision path.
    """
    if reason is None:
        return "config"

    reason_type = getattr(reason, "type", None) or (
        reason.get("type") if isinstance(reason, dict) else None
    )

    if reason_type == "permissionPromptTool":
        tool_result = getattr(reason, "tool_result", None) or (
            reason.get("tool_result") if isinstance(reason, dict) else None
        )
        classified = (
            tool_result.get("decisionClassification") if isinstance(tool_result, dict) else None
        )
        if classified in ("user_temporary", "user_permanent", "user_reject"):
            return classified
        return "user_temporary" if behavior == "allow" else "user_reject"

    if reason_type == "rule":
        rule = getattr(reason, "rule", None) or (
            reason.get("rule") if isinstance(reason, dict) else None
        )
        if rule is not None:
            src = getattr(rule, "source", None) or (
                rule.get("source") if isinstance(rule, dict) else ""
            )
            return _rule_source_to_otel_source(str(src), behavior)
        return "config"

    if reason_type == "hook":
        return "hook"

    # mode, classifier, subcommandResults, asyncAgent, sandboxOverride,
    # workingDir, safetyCheck, other → all map to config
    return "config"


# ---------------------------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------------------------

def _find_mcp_server_connection(
    tool_name: str,
    mcp_clients: list,
) -> Optional[Any]:
    """Find the MCPServerConnection for a given tool name."""
    if not tool_name.startswith("mcp__"):
        return None
    try:
        from claude_code.services.mcp.mcp_string_utils import mcp_info_from_string
        from claude_code.services.mcp.normalization import normalize_name_for_mcp
        mcp_info = mcp_info_from_string(tool_name)
        if not mcp_info:
            return None
        server_name = mcp_info.get("server_name") or mcp_info.get("serverName")
        for client in mcp_clients:
            client_name = getattr(client, "name", None) or (
                client.get("name") if isinstance(client, dict) else None
            )
            if client_name and normalize_name_for_mcp(client_name) == server_name:
                return client
    except ImportError:
        pass
    return None


def _get_mcp_server_type(tool_name: str, mcp_clients: list) -> McpServerType:
    """
    Extracts the MCP server transport type from a tool name.
    Returns the server type (stdio, sse, http, ws, sdk, etc.) for MCP tools,
    or None for built-in tools.
    """
    conn = _find_mcp_server_connection(tool_name, mcp_clients)
    if conn is None:
        return None
    conn_type = getattr(conn, "type", None) or (
        conn.get("type") if isinstance(conn, dict) else None
    )
    if conn_type == "connected":
        config = getattr(conn, "config", None) or (
            conn.get("config") if isinstance(conn, dict) else {}
        )
        if isinstance(config, dict):
            return config.get("type", "stdio")
        return getattr(config, "type", "stdio") or "stdio"
    return None


def _get_mcp_server_base_url(tool_name: str, mcp_clients: list) -> Optional[str]:
    """
    Extracts the MCP server base URL for a tool.
    Returns None for stdio servers, built-in tools, or disconnected servers.
    """
    conn = _find_mcp_server_connection(tool_name, mcp_clients)
    if conn is None:
        return None
    conn_type = getattr(conn, "type", None) or (
        conn.get("type") if isinstance(conn, dict) else None
    )
    if conn_type != "connected":
        return None
    try:
        from claude_code.services.mcp.utils import get_logging_safe_mcp_base_url
        config = getattr(conn, "config", None) or (
            conn.get("config") if isinstance(conn, dict) else {}
        )
        return get_logging_safe_mcp_base_url(config)
    except ImportError:
        return None


def _mcp_tool_details_for_analytics(
    tool_name: str,
    mcp_server_type: McpServerType,
    mcp_server_base_url: Optional[str],
) -> dict:
    try:
        from claude_code.services.analytics.metadata import mcp_tool_details_for_analytics
        return mcp_tool_details_for_analytics(tool_name, mcp_server_type, mcp_server_base_url)
    except ImportError:
        return {}


def _is_tool_search_enabled_optimistic() -> bool:
    try:
        from claude_code.utils.tool_search import is_tool_search_enabled_optimistic
        return is_tool_search_enabled_optimistic()
    except ImportError:
        return False


def _is_tool_search_tool_available(tools: list) -> bool:
    try:
        from claude_code.utils.tool_search import is_tool_search_tool_available
        return is_tool_search_tool_available(tools)
    except ImportError:
        return False


def _is_deferred_tool(tool: Any) -> bool:
    try:
        from claude_code.tools.tool_search_tool.prompt import is_deferred_tool
        return is_deferred_tool(tool)
    except ImportError:
        return False


def _get_tool_search_tool_name() -> str:
    try:
        from claude_code.tools.tool_search_tool.prompt import TOOL_SEARCH_TOOL_NAME
        return TOOL_SEARCH_TOOL_NAME
    except ImportError:
        return "ToolSearch"


def _extract_discovered_tool_names(messages: list) -> set:
    try:
        from claude_code.utils.tool_search import extract_discovered_tool_names
        return extract_discovered_tool_names(messages)
    except ImportError:
        return set()


# ---------------------------------------------------------------------------
# buildSchemaNotSentHint
# ---------------------------------------------------------------------------

def build_schema_not_sent_hint(
    tool: Any,
    messages: list,
    tools: list,
) -> Optional[str]:
    """
    Appended to Zod-style errors when a deferred tool wasn't in the
    discovered-tool set — re-runs the schema-filter scan dispatch-time to
    detect the mismatch. Null if the schema was sent.
    """
    # Optimistic gating: these gates prevent pointing at a ToolSearch that
    # isn't callable; occasional misfires cost one extra round-trip on an
    # already-failing path.
    if not _is_tool_search_enabled_optimistic():
        return None
    if not _is_tool_search_tool_available(tools):
        return None
    if not _is_deferred_tool(tool):
        return None
    discovered = _extract_discovered_tool_names(messages)
    if tool.name in discovered:
        return None
    tool_search_name = _get_tool_search_tool_name()
    return (
        f"\n\nThis tool's schema was not sent to the API — it was not in the "
        f"discovered-tool set derived from message history. "
        f"Without the schema in your prompt, typed parameters (arrays, numbers, "
        f"booleans) get emitted as strings and the client-side parser rejects them. "
        f"Load the tool first: call {tool_search_name} with query "
        f'"select:{tool.name}", then retry this call.'
    )


# ---------------------------------------------------------------------------
# Input validation helpers
# ---------------------------------------------------------------------------

def _validate_input_schema(tool: Any, input_data: dict) -> tuple[bool, Any, str]:
    """
    Validate tool input against its schema.

    Returns (ok, parsed_data, error_message).
    Mirrors TS: tool.inputSchema.safeParse(input).
    Uses jsonschema if available, otherwise passes through.
    """
    # If tool exposes an input_schema dict, try jsonschema validation
    schema_fn = getattr(tool, "input_schema", None)
    if schema_fn and callable(schema_fn):
        schema = schema_fn()
    else:
        # No schema — pass through
        return True, input_data, ""

    try:
        import jsonschema  # type: ignore
        try:
            jsonschema.validate(instance=input_data, schema=schema)
            return True, input_data, ""
        except jsonschema.ValidationError as e:
            return False, None, e.message
        except jsonschema.SchemaError as e:
            return False, None, str(e)
    except ImportError:
        # jsonschema not installed — skip validation
        return True, input_data, ""


def _format_zod_validation_error(tool_name: str, error_msg: str) -> str:
    try:
        from claude_code.utils.tool_errors import format_validation_error
        return format_validation_error(tool_name, error_msg)
    except ImportError:
        return f"{tool_name} tool input error: {error_msg}"


def _format_error(error: Any) -> str:
    try:
        from claude_code.utils.tool_errors import format_error
        return format_error(error)
    except ImportError:
        return str(error)


# ---------------------------------------------------------------------------
# Message creation helpers
# ---------------------------------------------------------------------------

def _create_user_message_raw(**kwargs: Any) -> Any:
    """
    Create a user message dict (or dataclass), mapping closely to TS
    createUserMessage(). Uses the messages util if available.
    """
    try:
        from claude_code.utils.messages import create_user_message
        content = kwargs.get("content", [])
        return create_user_message(content)
    except ImportError:
        pass
    # Fallback: plain dict
    return {
        "type": "user",
        "role": "user",
        "content": kwargs.get("content", []),
        "tool_use_result": kwargs.get("tool_use_result"),
        "source_tool_assistant_uuid": kwargs.get("source_tool_assistant_uuid"),
        "uuid": str(_uuid.uuid4()),
    }


def _create_progress_message(
    tool_use_id: str,
    parent_tool_use_id: str,
    data: Any,
) -> Any:
    try:
        from claude_code.utils.messages import create_progress_message
        return create_progress_message(
            tool_use_id=tool_use_id,
            parent_tool_use_id=parent_tool_use_id,
            data=data,
        )
    except ImportError:
        return {
            "type": "progress",
            "tool_use_id": tool_use_id,
            "parent_tool_use_id": parent_tool_use_id,
            "data": data,
        }


def _create_stop_hook_summary_message(
    hook_count: int,
    hook_infos: list,
    post_infos: list,
    has_blocks: bool,
    block_reason: Optional[str],
    has_deny: bool,
    suggestion: str,
    extra: Any,
    phase: str,
    duration_ms: int,
) -> Any:
    try:
        from claude_code.utils.messages import create_stop_hook_summary_message
        return create_stop_hook_summary_message(
            hook_count, hook_infos, post_infos, has_blocks, block_reason,
            has_deny, suggestion, extra, phase, duration_ms,
        )
    except ImportError:
        return {
            "type": "stop_hook_summary",
            "phase": phase,
            "hook_count": hook_count,
            "duration_ms": duration_ms,
        }


def _create_tool_result_stop_message(tool_use_id: str) -> dict:
    try:
        from claude_code.utils.messages import create_tool_result_stop_message
        return create_tool_result_stop_message(tool_use_id)
    except ImportError:
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": "Stopped",
            "is_error": True,
        }


def _create_attachment_message(**kwargs: Any) -> Any:
    try:
        from claude_code.utils.messages import create_attachment_message
        return create_attachment_message(**kwargs)
    except ImportError:
        return {"type": "attachment", **kwargs}


def _with_memory_correction_hint(msg: str) -> str:
    try:
        from claude_code.utils.messages import with_memory_correction_hint
        return with_memory_correction_hint(msg)
    except ImportError:
        return msg


def _count(items: list, predicate: Callable[[Any], bool]) -> int:
    return sum(1 for i in items if predicate(i))


def _get_next_image_paste_id(messages: list) -> int:
    """Find the next sequential imagePasteId across existing messages."""
    max_id = 0
    for message in messages:
        if isinstance(message, dict):
            paste_ids = message.get("image_paste_ids") or message.get("imagePasteIds") or []
        else:
            paste_ids = getattr(message, "image_paste_ids", None) or []
        for id_ in paste_ids:
            if id_ > max_id:
                max_id = id_
    return max_id + 1


# ---------------------------------------------------------------------------
# Stats / telemetry stubs
# ---------------------------------------------------------------------------

def _add_to_tool_duration(ms: int) -> None:
    try:
        from claude_code.bootstrap.state import add_to_tool_duration
        add_to_tool_duration(ms)
    except ImportError:
        pass


def _get_stats_store() -> Any:
    try:
        from claude_code.bootstrap.state import get_stats_store
        return get_stats_store()
    except ImportError:
        return None


def _start_session_activity(name: str) -> None:
    try:
        from claude_code.utils.session_activity import start_session_activity
        start_session_activity(name)
    except ImportError:
        pass


def _stop_session_activity(name: str) -> None:
    try:
        from claude_code.utils.session_activity import stop_session_activity
        stop_session_activity(name)
    except ImportError:
        pass


def _start_tool_span(name: str, attrs: dict, json_input: Optional[str]) -> None:
    try:
        from claude_code.utils.telemetry.session_tracing import start_tool_span
        start_tool_span(name, attrs, json_input)
    except ImportError:
        pass


def _end_tool_span(result: Optional[str] = None) -> None:
    try:
        from claude_code.utils.telemetry.session_tracing import end_tool_span
        end_tool_span(result)
    except ImportError:
        pass


def _start_tool_blocked_on_user_span() -> None:
    try:
        from claude_code.utils.telemetry.session_tracing import start_tool_blocked_on_user_span
        start_tool_blocked_on_user_span()
    except ImportError:
        pass


def _end_tool_blocked_on_user_span(decision: str, source: str) -> None:
    try:
        from claude_code.utils.telemetry.session_tracing import end_tool_blocked_on_user_span
        end_tool_blocked_on_user_span(decision, source)
    except ImportError:
        pass


def _start_tool_execution_span() -> None:
    try:
        from claude_code.utils.telemetry.session_tracing import start_tool_execution_span
        start_tool_execution_span()
    except ImportError:
        pass


def _end_tool_execution_span(opts: dict) -> None:
    try:
        from claude_code.utils.telemetry.session_tracing import end_tool_execution_span
        end_tool_execution_span(**opts)
    except ImportError:
        pass


def _add_tool_content_event(event_name: str, attrs: dict) -> None:
    try:
        from claude_code.utils.telemetry.session_tracing import add_tool_content_event
        add_tool_content_event(event_name, attrs)
    except ImportError:
        pass


def _is_beta_tracing_enabled() -> bool:
    try:
        from claude_code.utils.telemetry.session_tracing import is_beta_tracing_enabled
        return is_beta_tracing_enabled()
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Code-edit tool helpers
# ---------------------------------------------------------------------------

def _is_code_editing_tool(name: str) -> bool:
    try:
        from claude_code.hooks.tool_permission.permission_logging import is_code_editing_tool
        return is_code_editing_tool(name)
    except ImportError:
        return False


def _build_code_edit_tool_attributes(
    tool: Any, processed_input: Any, decision: str, source: str
) -> None:
    try:
        from claude_code.hooks.tool_permission.permission_logging import build_code_edit_tool_attributes
        from claude_code.bootstrap.state import get_code_edit_tool_decision_counter
        async def _run():
            attrs = await build_code_edit_tool_attributes(tool, processed_input, decision, source)
            counter = get_code_edit_tool_decision_counter()
            if counter:
                counter.add(1, attrs)
        asyncio.ensure_future(_run())
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Permission helpers
# ---------------------------------------------------------------------------

async def _resolve_hook_permission_decision(
    hook_permission_result: Any,
    tool: Any,
    processed_input: Any,
    tool_use_context: Any,
    can_use_tool: Any,
    assistant_message: Any,
    tool_use_id: str,
) -> Any:
    """
    Wrap resolveHookPermissionDecision from toolHooks.
    Returns an object with .decision and .input fields.
    """
    try:
        from claude_code.services.tools.tool_hooks import resolve_hook_permission_decision
        return await resolve_hook_permission_decision(
            hook_permission_result,
            tool,
            processed_input,
            tool_use_context,
            can_use_tool,
            assistant_message,
            tool_use_id,
        )
    except ImportError:
        pass

    # Fallback: auto-allow if we have no permission infrastructure
    class _DefaultResolved:
        input = processed_input

        @dataclass
        class _Decision:
            behavior: str = "allow"
            decision_reason: Any = None
            updated_input: Any = None
            user_modified: bool = False
            message: str = ""

        decision = _Decision()

    return _DefaultResolved()


async def _execute_permission_denied_hooks(
    tool_name: str,
    tool_use_id: str,
    processed_input: Any,
    reason: str,
    tool_use_context: Any,
    permission_mode: str,
    signal: Any,
) -> AsyncGenerator[Any, None]:
    try:
        from claude_code.utils.hooks import execute_permission_denied_hooks
        async for result in execute_permission_denied_hooks(
            tool_name, tool_use_id, processed_input, reason,
            tool_use_context, permission_mode, signal,
        ):
            yield result
    except ImportError:
        return


# ---------------------------------------------------------------------------
# Tool result storage helpers
# ---------------------------------------------------------------------------

async def _process_pre_mapped_tool_result_block(
    block: dict, tool_name: str, max_chars: int
) -> dict:
    try:
        from claude_code.utils.tool_result_storage import process_pre_mapped_tool_result_block
        return await process_pre_mapped_tool_result_block(block, tool_name, max_chars)
    except ImportError:
        return block


async def _process_tool_result_block(tool: Any, tool_use_result: Any, tool_use_id: str) -> dict:
    try:
        from claude_code.utils.tool_result_storage import process_tool_result_block
        return await process_tool_result_block(tool, tool_use_result, tool_use_id)
    except ImportError:
        content = _json_stringify(tool_use_result) if not isinstance(tool_use_result, str) else tool_use_result
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
        }


def _get_file_extension_for_analytics(path: str) -> Optional[str]:
    try:
        from claude_code.services.analytics.metadata import get_file_extension_for_analytics
        return get_file_extension_for_analytics(path)
    except ImportError:
        import os.path
        _, ext = os.path.splitext(path)
        return ext or None


def _get_file_extensions_from_bash_command(command: str, file_path: Optional[str]) -> Optional[str]:
    try:
        from claude_code.services.analytics.metadata import get_file_extensions_from_bash_command
        return get_file_extensions_from_bash_command(command, file_path)
    except ImportError:
        return None


def _is_tool_details_logging_enabled() -> bool:
    try:
        from claude_code.services.analytics.metadata import is_tool_details_logging_enabled
        return is_tool_details_logging_enabled()
    except ImportError:
        return False


def _extract_tool_input_for_telemetry(processed_input: Any) -> Any:
    try:
        from claude_code.services.analytics.metadata import extract_tool_input_for_telemetry
        return extract_tool_input_for_telemetry(processed_input)
    except ImportError:
        return None


def _extract_mcp_tool_details(tool_name: str) -> Optional[dict]:
    try:
        from claude_code.services.analytics.metadata import extract_mcp_tool_details
        return extract_mcp_tool_details(tool_name)
    except ImportError:
        return None


def _extract_skill_name(tool_name: str, processed_input: Any) -> Optional[str]:
    try:
        from claude_code.services.analytics.metadata import extract_skill_name
        return extract_skill_name(tool_name, processed_input)
    except ImportError:
        return None


def _parse_git_commit_id(stdout: str) -> Optional[str]:
    try:
        from claude_code.tools.shared.git_operation_tracking import parse_git_commit_id
        return parse_git_commit_id(stdout)
    except ImportError:
        return None


def _get_mcp_server_scope_from_tool_name(tool_name: str) -> Optional[str]:
    try:
        from claude_code.services.mcp.utils import get_mcp_server_scope_from_tool_name
        return get_mcp_server_scope_from_tool_name(tool_name)
    except ImportError:
        return None


def _speculative_classifier_check(
    command: str,
    tool_permission_context: Any,
    signal: Any,
    is_non_interactive: bool,
) -> None:
    try:
        from claude_code.tools.bash_tool.bash_permissions import start_speculative_classifier_check
        start_speculative_classifier_check(
            command, tool_permission_context, signal, is_non_interactive
        )
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Constant tool name references
# ---------------------------------------------------------------------------

def _bash_tool_name() -> str:
    try:
        from claude_code.constants.tools import BASH_TOOL_NAME
        return BASH_TOOL_NAME
    except ImportError:
        return "Bash"


def _file_read_tool_name() -> str:
    try:
        from claude_code.constants.tools import FILE_READ_TOOL_NAME
        return FILE_READ_TOOL_NAME
    except ImportError:
        return "Read"


def _file_edit_tool_name() -> str:
    try:
        from claude_code.constants.tools import FILE_EDIT_TOOL_NAME
        return FILE_EDIT_TOOL_NAME
    except ImportError:
        return "Edit"


def _file_write_tool_name() -> str:
    try:
        from claude_code.constants.tools import FILE_WRITE_TOOL_NAME
        return FILE_WRITE_TOOL_NAME
    except ImportError:
        return "Write"


def _notebook_edit_tool_name() -> str:
    try:
        from claude_code.constants.tools import NOTEBOOK_EDIT_TOOL_NAME
        return NOTEBOOK_EDIT_TOOL_NAME
    except ImportError:
        return "NotebookEdit"


def _powershell_tool_name() -> str:
    try:
        from claude_code.constants.tools import POWERSHELL_TOOL_NAME
        return POWERSHELL_TOOL_NAME
    except ImportError:
        return "PowerShell"


# ---------------------------------------------------------------------------
# Stream<T> equivalent (async queue)
# ---------------------------------------------------------------------------

class Stream(asyncio.Queue):
    """
    Minimal async stream: producer enqueues items, consumer iterates.
    Python equivalent of the TS Stream<T> utility.

    A sentinel (None or _DONE marker) signals end-of-stream.
    """

    _DONE = object()  # sentinel

    def enqueue(self, item: Any) -> None:
        self.put_nowait(item)

    def done(self) -> None:
        self.put_nowait(self._DONE)

    def error(self, exc: Exception) -> None:
        self.put_nowait(exc)

    async def __aiter__(self):
        while True:
            item = await self.get()
            if item is self._DONE:
                break
            if isinstance(item, Exception):
                raise item
            yield item


# ---------------------------------------------------------------------------
# Pre/Post tool hook result types (mirrors TS discriminated unions)
# ---------------------------------------------------------------------------

@dataclass
class HookResultMessage:
    type: str = "message"
    message: Any = None


@dataclass
class HookResultHookPermissionResult:
    type: str = "hookPermissionResult"
    hook_permission_result: Any = None


@dataclass
class HookResultHookUpdatedInput:
    type: str = "hookUpdatedInput"
    updated_input: Any = None


@dataclass
class HookResultPreventContinuation:
    type: str = "preventContinuation"
    should_prevent_continuation: bool = False


@dataclass
class HookResultStopReason:
    type: str = "stopReason"
    stop_reason: Optional[str] = None


@dataclass
class HookResultAdditionalContext:
    type: str = "additionalContext"
    message: Any = None


@dataclass
class HookResultStop:
    type: str = "stop"


# ---------------------------------------------------------------------------
# runPreToolUseHooks wrapper (mirrors TS runPreToolUseHooks)
# ---------------------------------------------------------------------------

async def _run_pre_tool_use_hooks(
    tool_use_context: Any,
    tool: Any,
    processed_input: Any,
    tool_use_id: str,
    message_id: str,
    request_id: Optional[str],
    mcp_server_type: McpServerType,
    mcp_server_base_url: Optional[str],
) -> AsyncGenerator[Any, None]:
    try:
        from claude_code.services.tools.tool_hooks import run_pre_tool_use_hooks
        async for result in run_pre_tool_use_hooks(
            tool_use_context,
            tool,
            processed_input,
            tool_use_id,
            message_id,
            request_id,
            mcp_server_type,
            mcp_server_base_url,
        ):
            yield result
    except ImportError:
        return
    except TypeError:
        # Fallback: older signature run_pre_tool_use_hooks(tool, input, context)
        try:
            from claude_code.services.tools.tool_hooks import run_pre_tool_use_hooks
            async for result in run_pre_tool_use_hooks(tool, processed_input, tool_use_context):
                yield result
        except Exception:
            return


# ---------------------------------------------------------------------------
# runPostToolUseHooks wrapper
# ---------------------------------------------------------------------------

async def _run_post_tool_use_hooks(
    tool_use_context: Any,
    tool: Any,
    tool_use_id: str,
    message_id: str,
    processed_input: Any,
    tool_output: Any,
    request_id: Optional[str],
    mcp_server_type: McpServerType,
    mcp_server_base_url: Optional[str],
) -> AsyncGenerator[Any, None]:
    try:
        from claude_code.services.tools.tool_hooks import run_post_tool_use_hooks
        async for result in run_post_tool_use_hooks(
            tool_use_context,
            tool,
            tool_use_id,
            message_id,
            processed_input,
            tool_output,
            request_id,
            mcp_server_type,
            mcp_server_base_url,
        ):
            yield result
    except ImportError:
        return
    except TypeError:
        try:
            from claude_code.services.tools.tool_hooks import run_post_tool_use_hooks
            async for result in run_post_tool_use_hooks(tool, processed_input, tool_output, tool_use_context):
                yield result
        except Exception:
            return


# ---------------------------------------------------------------------------
# runPostToolUseFailureHooks wrapper
# ---------------------------------------------------------------------------

async def _run_post_tool_use_failure_hooks(
    tool_use_context: Any,
    tool: Any,
    tool_use_id: str,
    message_id: str,
    processed_input: Any,
    content: str,
    is_interrupt: bool,
    request_id: Optional[str],
    mcp_server_type: McpServerType,
    mcp_server_base_url: Optional[str],
) -> AsyncGenerator[Any, None]:
    try:
        from claude_code.services.tools.tool_hooks import run_post_tool_use_failure_hooks
        async for result in run_post_tool_use_failure_hooks(
            tool_use_context,
            tool,
            tool_use_id,
            message_id,
            processed_input,
            content,
            is_interrupt,
            request_id,
            mcp_server_type,
            mcp_server_base_url,
        ):
            yield result
    except ImportError:
        return
    except TypeError:
        try:
            from claude_code.services.tools.tool_hooks import run_post_tool_use_failure_hooks
            async for result in run_post_tool_use_failure_hooks(
                tool, processed_input, content, tool_use_context
            ):
                yield result
        except Exception:
            return


# ---------------------------------------------------------------------------
# StopHookInfo
# ---------------------------------------------------------------------------

@dataclass
class StopHookInfo:
    command: str
    duration_ms: int


# ---------------------------------------------------------------------------
# Core: checkPermissionsAndCallTool
# ---------------------------------------------------------------------------

async def check_permissions_and_call_tool(
    tool: Any,
    tool_use_id: str,
    input_data: dict,
    tool_use_context: Any,
    can_use_tool: Any,
    assistant_message: Any,
    message_id: str,
    request_id: Optional[str],
    mcp_server_type: McpServerType,
    mcp_server_base_url: Optional[str],
    on_tool_progress: Callable[[Any], None],
) -> List[MessageUpdateLazy]:
    """
    Full permission-check + tool-call pipeline.
    Returns a list of MessageUpdateLazy to deliver to the conversation.

    Mirrors TS checkPermissionsAndCallTool().
    """
    BASH = _bash_tool_name()
    FILE_READ = _file_read_tool_name()
    FILE_EDIT = _file_edit_tool_name()
    FILE_WRITE = _file_write_tool_name()
    NOTEBOOK_EDIT = _notebook_edit_tool_name()
    POWERSHELL = _powershell_tool_name()

    # ---------- Step 1: Schema validation ----------
    ok, parsed_data, validation_err = _validate_input_schema(tool, input_data)
    if not ok:
        error_content = _format_zod_validation_error(tool.name, validation_err)

        # Add schema-not-sent hint for deferred tools
        messages = getattr(tool_use_context, "messages", []) or []
        tools = getattr(getattr(tool_use_context, "options", None), "tools", []) or []
        schema_hint = build_schema_not_sent_hint(tool, messages, tools)
        if schema_hint:
            _log_event("tengu_deferred_tool_schema_not_sent", {
                "toolName": _sanitize_tool_name(tool.name),
                "isMcp": getattr(tool, "is_mcp", False) or False,
            })
            error_content += schema_hint

        _log_for_debugging(
            f"{tool.name} tool input error: {error_content[:200]}"
        )
        _log_event("tengu_tool_use_error", {
            "error": "InputValidationError",
            "errorDetails": error_content[:2000],
            "messageID": message_id,
            "toolName": _sanitize_tool_name(tool.name),
            "isMcp": getattr(tool, "is_mcp", False) or False,
            **({"queryChainId": tool_use_context.query_tracking.chain_id}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **({"queryDepth": tool_use_context.query_tracking.depth}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **({"mcpServerType": mcp_server_type} if mcp_server_type else {}),
            **({"mcpServerBaseUrl": mcp_server_base_url} if mcp_server_base_url else {}),
            **({"requestId": request_id} if request_id else {}),
            **_mcp_tool_details_for_analytics(tool.name, mcp_server_type, mcp_server_base_url),
        })
        return [
            MessageUpdateLazy(
                message=_create_user_message_raw(
                    content=[{
                        "type": "tool_result",
                        "content": f"<tool_use_error>InputValidationError: {error_content}</tool_use_error>",
                        "is_error": True,
                        "tool_use_id": tool_use_id,
                    }],
                    tool_use_result=f"InputValidationError: {validation_err}",
                    source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
                )
            )
        ]

    # Use parsed data from this point forward
    processed_input = parsed_data if parsed_data is not None else input_data

    # ---------- Step 2: Semantic input validation (tool-specific) ----------
    validate_fn = getattr(tool, "validate_input", None)
    if validate_fn and callable(validate_fn):
        try:
            is_valid_call = await validate_fn(processed_input, tool_use_context)
            if is_valid_call is not None and getattr(is_valid_call, "result", True) is False:
                _log_for_debugging(
                    f"{tool.name} tool validation error: {str(getattr(is_valid_call, 'message', ''))[:200]}"
                )
                _log_event("tengu_tool_use_error", {
                    "messageID": message_id,
                    "toolName": _sanitize_tool_name(tool.name),
                    "error": getattr(is_valid_call, "message", ""),
                    "errorCode": getattr(is_valid_call, "error_code", None),
                    "isMcp": getattr(tool, "is_mcp", False) or False,
                    **({"mcpServerType": mcp_server_type} if mcp_server_type else {}),
                    **({"mcpServerBaseUrl": mcp_server_base_url} if mcp_server_base_url else {}),
                    **({"requestId": request_id} if request_id else {}),
                    **_mcp_tool_details_for_analytics(
                        tool.name, mcp_server_type, mcp_server_base_url
                    ),
                })
                return [
                    MessageUpdateLazy(
                        message=_create_user_message_raw(
                            content=[{
                                "type": "tool_result",
                                "content": f"<tool_use_error>{is_valid_call.message}</tool_use_error>",
                                "is_error": True,
                                "tool_use_id": tool_use_id,
                            }],
                            tool_use_result=f"Error: {is_valid_call.message}",
                            source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
                        )
                    )
                ]
        except Exception:
            pass  # Non-critical: skip if validate_input raises unexpectedly

    # ---------- Step 2b: Speculatively start bash allow-classifier ----------
    # (parallel with pre-tool hooks and permission dialog setup)
    if isinstance(processed_input, dict) and tool.name == BASH and "command" in processed_input:
        app_state_fn = getattr(tool_use_context, "get_app_state", None)
        app_state = app_state_fn() if app_state_fn else None
        tool_perm_ctx = getattr(app_state, "tool_permission_context", None) if app_state else None
        abort_ctrl = getattr(tool_use_context, "abort_controller", None)
        signal = getattr(abort_ctrl, "signal", None)
        is_non_interactive = getattr(
            getattr(tool_use_context, "options", None), "is_non_interactive_session", False
        )
        if tool_perm_ctx:
            _speculative_classifier_check(
                processed_input["command"],
                tool_perm_ctx,
                signal,
                is_non_interactive,
            )

    resulting_messages: List[MessageUpdateLazy] = []

    # ---------- Step 2c: Strip _simulatedSedEdit (defense-in-depth) ----------
    # This field is internal-only — it must only be injected by the permission
    # system after user approval. Strip any model-provided copy.
    if (
        tool.name == BASH
        and isinstance(processed_input, dict)
        and "_simulatedSedEdit" in processed_input
    ):
        processed_input = {k: v for k, v in processed_input.items() if k != "_simulatedSedEdit"}

    # ---------- Step 2d: Backfill observable input (shallow clone for hooks) ----------
    # Keeps call() seeing original model values; hooks see enriched clone.
    call_input = processed_input
    backfill_fn = getattr(tool, "backfill_observable_input", None)
    backfilled_clone = None
    if backfill_fn and callable(backfill_fn) and isinstance(processed_input, dict):
        backfilled_clone = dict(processed_input)
        backfill_fn(backfilled_clone)
        processed_input = backfilled_clone

    # ---------- Step 3: Run PreToolUse hooks ----------
    should_prevent_continuation = False
    stop_reason: Optional[str] = None
    hook_permission_result = None
    pre_tool_hook_infos: List[StopHookInfo] = []
    pre_tool_hook_start = _now_ms()

    async for result in _run_pre_tool_use_hooks(
        tool_use_context,
        tool,
        processed_input,
        tool_use_id,
        message_id,
        request_id,
        mcp_server_type,
        mcp_server_base_url,
    ):
        result_type = result.type if hasattr(result, "type") else result.get("type", "") if isinstance(result, dict) else ""

        if result_type == "message":
            msg_wrap = result.message if hasattr(result, "message") else result.get("message")
            if msg_wrap is not None:
                inner_msg = msg_wrap.message if hasattr(msg_wrap, "message") else msg_wrap
                inner_type = (
                    inner_msg.get("type") if isinstance(inner_msg, dict)
                    else getattr(inner_msg, "type", "")
                )
                if inner_type == "progress":
                    on_tool_progress(inner_msg)
                else:
                    resulting_messages.append(msg_wrap if isinstance(msg_wrap, MessageUpdateLazy) else MessageUpdateLazy(message=msg_wrap))
                    # Extract hook timing info from attachment messages
                    att = (
                        inner_msg.get("attachment") if isinstance(inner_msg, dict)
                        else getattr(inner_msg, "attachment", None)
                    )
                    if att is not None:
                        cmd = att.get("command") if isinstance(att, dict) else getattr(att, "command", None)
                        dur = att.get("durationMs") if isinstance(att, dict) else getattr(att, "duration_ms", None)
                        if cmd is not None and dur is not None:
                            pre_tool_hook_infos.append(StopHookInfo(command=cmd, duration_ms=dur))

        elif result_type == "hookPermissionResult":
            hook_permission_result = (
                result.hook_permission_result if hasattr(result, "hook_permission_result")
                else result.get("hookPermissionResult")
            )

        elif result_type == "hookUpdatedInput":
            updated = (
                result.updated_input if hasattr(result, "updated_input")
                else result.get("updatedInput")
            )
            if updated is not None:
                # Hook provided updatedInput without making a permission decision (passthrough)
                processed_input = updated

        elif result_type == "preventContinuation":
            should_prevent_continuation = (
                result.should_prevent_continuation if hasattr(result, "should_prevent_continuation")
                else result.get("shouldPreventContinuation", False)
            )

        elif result_type == "stopReason":
            stop_reason = (
                result.stop_reason if hasattr(result, "stop_reason")
                else result.get("stopReason")
            )

        elif result_type == "additionalContext":
            msg_wrap = result.message if hasattr(result, "message") else result.get("message")
            if msg_wrap is not None:
                resulting_messages.append(
                    msg_wrap if isinstance(msg_wrap, MessageUpdateLazy)
                    else MessageUpdateLazy(message=msg_wrap)
                )

        elif result_type == "stop":
            stats = _get_stats_store()
            if stats:
                stats.observe("pre_tool_hook_duration_ms", _now_ms() - pre_tool_hook_start)
            tool_result_stop = _create_tool_result_stop_message(tool_use_id)
            resulting_messages.append(
                MessageUpdateLazy(
                    message=_create_user_message_raw(
                        content=[tool_result_stop],
                        tool_use_result=f"Error: {stop_reason}",
                        source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
                    )
                )
            )
            return resulting_messages

    pre_tool_hook_duration_ms = _now_ms() - pre_tool_hook_start
    stats = _get_stats_store()
    if stats:
        stats.observe("pre_tool_hook_duration_ms", pre_tool_hook_duration_ms)

    if pre_tool_hook_duration_ms >= _SLOW_PHASE_LOG_THRESHOLD_MS:
        _log_for_debugging(
            f"Slow PreToolUse hooks: {pre_tool_hook_duration_ms}ms for {tool.name} "
            f"({len(pre_tool_hook_infos)} hooks)",
            {"level": "info"},
        )

    # Emit PreToolUse summary immediately so it's visible while the tool executes.
    # Use wall-clock time (not sum of individual durations) since hooks run in parallel.
    if os.environ.get("USER_TYPE") == "ant" and pre_tool_hook_infos:
        if pre_tool_hook_duration_ms > HOOK_TIMING_DISPLAY_THRESHOLD_MS:
            resulting_messages.append(
                MessageUpdateLazy(
                    message=_create_stop_hook_summary_message(
                        len(pre_tool_hook_infos),
                        pre_tool_hook_infos,
                        [],
                        False,
                        None,
                        False,
                        "suggestion",
                        None,
                        "PreToolUse",
                        pre_tool_hook_duration_ms,
                    )
                )
            )

    # ---------- Step 4: Build tool span attributes ----------
    tool_attributes: dict = {}
    if isinstance(processed_input, dict):
        if tool.name == FILE_READ and "file_path" in processed_input:
            tool_attributes["file_path"] = str(processed_input["file_path"])
        elif tool.name in (FILE_EDIT, FILE_WRITE) and "file_path" in processed_input:
            tool_attributes["file_path"] = str(processed_input["file_path"])
        elif tool.name == BASH and "command" in processed_input:
            tool_attributes["full_command"] = processed_input["command"]

    _start_tool_span(
        tool.name,
        tool_attributes,
        _json_stringify(processed_input) if _is_beta_tracing_enabled() else None,
    )
    _start_tool_blocked_on_user_span()

    # ---------- Step 5: Permission check ----------
    app_state_fn = getattr(tool_use_context, "get_app_state", None)
    app_state = app_state_fn() if app_state_fn else None
    tool_perm_ctx = getattr(app_state, "tool_permission_context", None) if app_state else None
    permission_mode = getattr(tool_perm_ctx, "mode", "default") if tool_perm_ctx else "default"
    permission_start = _now_ms()

    resolved = await _resolve_hook_permission_decision(
        hook_permission_result,
        tool,
        processed_input,
        tool_use_context,
        can_use_tool,
        assistant_message,
        tool_use_id,
    )
    permission_decision = resolved.decision
    processed_input = resolved.input

    permission_duration_ms = _now_ms() - permission_start
    # In auto mode, canUseTool awaits the classifier — log if slow
    if (
        permission_duration_ms >= _SLOW_PHASE_LOG_THRESHOLD_MS
        and permission_mode == "auto"
    ):
        _log_for_debugging(
            f"Slow permission decision: {permission_duration_ms}ms for {tool.name} "
            f"(mode={permission_mode}, behavior={permission_decision.behavior})",
            {"level": "info"},
        )

    # Emit tool_decision OTel event (headless path)
    tool_decisions = getattr(tool_use_context, "tool_decisions", None)
    if (
        permission_decision.behavior != "ask"
        and (tool_decisions is None or tool_use_id not in tool_decisions)
    ):
        decision_str = "accept" if permission_decision.behavior == "allow" else "reject"
        source = _decision_reason_to_otel_source(
            getattr(permission_decision, "decision_reason", None),
            permission_decision.behavior,
        )
        _log_otel_event("tool_decision", {
            "decision": decision_str,
            "source": source,
            "tool_name": _sanitize_tool_name(tool.name),
        })

        # Increment code-edit tool decision counter for headless mode
        if _is_code_editing_tool(tool.name):
            _build_code_edit_tool_attributes(tool, processed_input, decision_str, source)

    # Add attachment message if permission was granted/denied by PermissionRequest hook
    decision_reason = getattr(permission_decision, "decision_reason", None)
    reason_type = getattr(decision_reason, "type", None) if decision_reason else None
    hook_name = getattr(decision_reason, "hook_name", None) if decision_reason else None
    if (
        reason_type == "hook"
        and hook_name == "PermissionRequest"
        and permission_decision.behavior != "ask"
    ):
        resulting_messages.append(
            MessageUpdateLazy(
                message=_create_attachment_message(
                    type="hook_permission_decision",
                    decision=permission_decision.behavior,
                    tool_use_id=tool_use_id,
                    hook_event="PermissionRequest",
                )
            )
        )

    # ---------- Step 6: Handle permission denied ----------
    if permission_decision.behavior != "allow":
        _log_for_debugging(f"{tool.name} tool permission denied")
        decision_info = tool_decisions.get(tool_use_id) if tool_decisions else None
        _end_tool_blocked_on_user_span(
            "reject",
            (decision_info.source if decision_info else None) or "unknown",
        )
        _end_tool_span()

        _log_event("tengu_tool_use_can_use_tool_rejected", {
            "messageID": message_id,
            "toolName": _sanitize_tool_name(tool.name),
            **({"queryChainId": tool_use_context.query_tracking.chain_id}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **({"queryDepth": tool_use_context.query_tracking.depth}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **({"mcpServerType": mcp_server_type} if mcp_server_type else {}),
            **({"mcpServerBaseUrl": mcp_server_base_url} if mcp_server_base_url else {}),
            **({"requestId": request_id} if request_id else {}),
            **_mcp_tool_details_for_analytics(tool.name, mcp_server_type, mcp_server_base_url),
        })

        err_message = getattr(permission_decision, "message", None)
        # Only use generic "Execution stopped" message if we don't have a detailed hook message
        if should_prevent_continuation and not err_message:
            err_message = (
                f"Execution stopped by PreToolUse hook"
                + (f": {stop_reason}" if stop_reason else "")
            )

        # Build top-level content: tool_result (text-only for is_error compat) + images alongside
        message_content: list = [
            {
                "type": "tool_result",
                "content": err_message,
                "is_error": True,
                "tool_use_id": tool_use_id,
            }
        ]

        # Add image blocks at top level (not inside tool_result with is_error)
        reject_content_blocks: Optional[list] = None
        if permission_decision.behavior == "ask":
            reject_content_blocks = getattr(permission_decision, "content_blocks", None)
        if reject_content_blocks:
            message_content.extend(reject_content_blocks)

        # Generate sequential imagePasteIds
        reject_image_ids: Optional[list] = None
        if reject_content_blocks:
            image_count = _count(
                reject_content_blocks,
                lambda b: (b.get("type") if isinstance(b, dict) else getattr(b, "type", "")) == "image",
            )
            if image_count > 0:
                messages_list = getattr(tool_use_context, "messages", []) or []
                start_id = _get_next_image_paste_id(messages_list)
                reject_image_ids = list(range(start_id, start_id + image_count))

        resulting_messages.append(
            MessageUpdateLazy(
                message=_create_user_message_raw(
                    content=message_content,
                    image_paste_ids=reject_image_ids,
                    tool_use_result=f"Error: {err_message}",
                    source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
                )
            )
        )

        # Run PermissionDenied hooks for auto-mode classifier denials
        try:
            from claude_code.utils.feature_flags import feature
            has_transcript_classifier = feature("TRANSCRIPT_CLASSIFIER")
        except ImportError:
            has_transcript_classifier = False

        if (
            has_transcript_classifier
            and reason_type == "classifier"
            and getattr(decision_reason, "classifier", "") == "auto-mode"
        ):
            hook_says_retry = False
            abort_ctrl = getattr(tool_use_context, "abort_controller", None)
            signal = getattr(abort_ctrl, "signal", None)
            async for result in _execute_permission_denied_hooks(
                tool.name,
                tool_use_id,
                processed_input,
                getattr(decision_reason, "reason", "Permission denied"),
                tool_use_context,
                permission_mode,
                signal,
            ):
                if getattr(result, "retry", False):
                    hook_says_retry = True
            if hook_says_retry:
                resulting_messages.append(
                    MessageUpdateLazy(
                        message=_create_user_message_raw(
                            content="The PermissionDenied hook indicated this command is now approved. "
                                    "You may retry it if you would like.",
                            is_meta=True,
                        )
                    )
                )

        return resulting_messages

    # ---------- Step 7: Permission allowed — proceed to execution ----------
    _log_event("tengu_tool_use_can_use_tool_allowed", {
        "messageID": message_id,
        "toolName": _sanitize_tool_name(tool.name),
        **({"queryChainId": tool_use_context.query_tracking.chain_id}
           if getattr(tool_use_context, "query_tracking", None) else {}),
        **({"queryDepth": tool_use_context.query_tracking.depth}
           if getattr(tool_use_context, "query_tracking", None) else {}),
        **({"mcpServerType": mcp_server_type} if mcp_server_type else {}),
        **({"mcpServerBaseUrl": mcp_server_base_url} if mcp_server_base_url else {}),
        **({"requestId": request_id} if request_id else {}),
        **_mcp_tool_details_for_analytics(tool.name, mcp_server_type, mcp_server_base_url),
    })

    # Use the updated input from permissions if provided.
    # (Don't overwrite if None — processedInput may have been modified by passthrough hooks)
    updated_input = getattr(permission_decision, "updated_input", None)
    if updated_input is not None:
        processed_input = updated_input

    # Prepare tool parameters for logging (gated by OTEL_LOG_TOOL_DETAILS)
    telemetry_tool_input = _extract_tool_input_for_telemetry(processed_input)
    tool_parameters: dict = {}
    if _is_tool_details_logging_enabled() and isinstance(processed_input, dict):
        if tool.name == BASH and "command" in processed_input:
            cmd_parts = processed_input["command"].strip().split()
            bash_command = cmd_parts[0] if cmd_parts else ""
            tool_parameters = {
                "bash_command": bash_command,
                "full_command": processed_input["command"],
                **({"timeout": processed_input["timeout"]} if "timeout" in processed_input else {}),
                **({"description": processed_input["description"]} if "description" in processed_input else {}),
                **({"dangerouslyDisableSandbox": processed_input["dangerouslyDisableSandbox"]}
                   if "dangerouslyDisableSandbox" in processed_input else {}),
            }
        mcp_details = _extract_mcp_tool_details(tool.name)
        if mcp_details:
            tool_parameters["mcp_server_name"] = mcp_details.get("serverName") or mcp_details.get("server_name")
            tool_parameters["mcp_tool_name"] = mcp_details.get("mcpToolName") or mcp_details.get("mcp_tool_name")
        skill_name = _extract_skill_name(tool.name, processed_input)
        if skill_name:
            tool_parameters["skill_name"] = skill_name

    decision_info = tool_decisions.get(tool_use_id) if tool_decisions else None
    _end_tool_blocked_on_user_span(
        (decision_info.decision if decision_info else None) or "unknown",
        (decision_info.source if decision_info else None) or "unknown",
    )
    _start_tool_execution_span()

    start_time = _now_ms()
    _start_session_activity("tool_exec")

    # Reconcile processedInput / callInput (preserve original file_path for transcripts)
    if (
        backfilled_clone is not None
        and processed_input is not call_input
        and isinstance(processed_input, dict)
        and "file_path" in processed_input
        and "file_path" in (call_input or {})
        and processed_input.get("file_path") == backfilled_clone.get("file_path")
    ):
        call_input = {**processed_input, "file_path": call_input["file_path"]}
    elif processed_input is not backfilled_clone:
        call_input = processed_input

    try:
        # ---------- Step 8: Call the tool ----------
        call_fn = getattr(tool, "call", None)
        if call_fn is None or not callable(call_fn):
            raise RuntimeError(f"Tool {tool.name!r} has no callable call() method")

        def _on_progress(progress: Any) -> None:
            on_tool_progress({
                "toolUseID": progress.get("toolUseID") if isinstance(progress, dict)
                             else getattr(progress, "tool_use_id", tool_use_id),
                "data": progress.get("data") if isinstance(progress, dict)
                        else getattr(progress, "data", None),
            })

        result = await call_fn(
            call_input,
            {**vars(tool_use_context), "tool_use_id": tool_use_id,
             "user_modified": getattr(permission_decision, "user_modified", False) or False}
            if hasattr(tool_use_context, "__dict__") else tool_use_context,
            can_use_tool,
            assistant_message,
            _on_progress,
        )

        duration_ms = _now_ms() - start_time
        _add_to_tool_duration(duration_ms)

        # Log tool content output as span event if enabled
        if isinstance(result, dict) and result.get("data") and isinstance(result["data"], dict):
            content_attributes: dict = {}
            data = result["data"]

            if tool.name == FILE_READ and "content" in data:
                if isinstance(processed_input, dict) and "file_path" in processed_input:
                    content_attributes["file_path"] = str(processed_input["file_path"])
                content_attributes["content"] = str(data["content"])

            if tool.name in (FILE_EDIT, FILE_WRITE) and isinstance(processed_input, dict) and "file_path" in processed_input:
                content_attributes["file_path"] = str(processed_input["file_path"])
                if tool.name == FILE_EDIT and "diff" in data:
                    content_attributes["diff"] = str(data["diff"])
                if tool.name == FILE_WRITE and "content" in processed_input:
                    content_attributes["content"] = str(processed_input["content"])

            if tool.name == BASH and isinstance(processed_input, dict) and "command" in processed_input:
                content_attributes["bash_command"] = processed_input["command"]
                if "output" in data:
                    content_attributes["output"] = str(data["output"])

            if content_attributes:
                _add_tool_content_event("tool.output", content_attributes)

        # Capture structured output
        if isinstance(result, dict) and "structured_output" in result:
            resulting_messages.append(
                MessageUpdateLazy(
                    message=_create_attachment_message(
                        type="structured_output",
                        data=result["structured_output"],
                    )
                )
            )

        _end_tool_execution_span({"success": True})
        tool_result_str = (
            _json_stringify(result.get("data"))
            if isinstance(result, dict) and result.get("data") is not None
            else str(result.get("data", "") if isinstance(result, dict) else result or "")
        )
        _end_tool_span(tool_result_str)

        # Map tool result to API format (cache for reuse)
        map_fn = getattr(tool, "map_tool_result_to_tool_result_block_param", None)
        if map_fn and callable(map_fn):
            mapped_tool_result_block = map_fn(
                result.get("data") if isinstance(result, dict) else result,
                tool_use_id,
            )
        else:
            tool_data = result.get("data") if isinstance(result, dict) else result
            mapped_tool_result_block = {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": _json_stringify(tool_data) if not isinstance(tool_data, str) else tool_data,
            }

        mapped_content = (
            mapped_tool_result_block.get("content")
            if isinstance(mapped_tool_result_block, dict)
            else getattr(mapped_tool_result_block, "content", None)
        )
        tool_result_size_bytes = (
            0 if mapped_content is None
            else len(mapped_content) if isinstance(mapped_content, str)
            else len(_json_stringify(mapped_content))
        )

        # Extract file extension for analytics
        file_extension = None
        if isinstance(processed_input, dict):
            if tool.name in (FILE_READ, FILE_EDIT, FILE_WRITE) and "file_path" in processed_input:
                file_extension = _get_file_extension_for_analytics(str(processed_input["file_path"]))
            elif tool.name == NOTEBOOK_EDIT and "notebook_path" in processed_input:
                file_extension = _get_file_extension_for_analytics(str(processed_input["notebook_path"]))
            elif tool.name == BASH and "command" in processed_input:
                sim_edit = processed_input.get("_simulatedSedEdit")
                file_extension = _get_file_extensions_from_bash_command(
                    processed_input["command"],
                    sim_edit.get("filePath") if isinstance(sim_edit, dict) else None,
                )

        _log_event("tengu_tool_use_success", {
            "messageID": message_id,
            "toolName": _sanitize_tool_name(tool.name),
            "isMcp": getattr(tool, "is_mcp", False) or False,
            "durationMs": duration_ms,
            "preToolHookDurationMs": pre_tool_hook_duration_ms,
            "toolResultSizeBytes": tool_result_size_bytes,
            **({"fileExtension": file_extension} if file_extension is not None else {}),
            **({"queryChainId": tool_use_context.query_tracking.chain_id}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **({"queryDepth": tool_use_context.query_tracking.depth}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **({"mcpServerType": mcp_server_type} if mcp_server_type else {}),
            **({"mcpServerBaseUrl": mcp_server_base_url} if mcp_server_base_url else {}),
            **({"requestId": request_id} if request_id else {}),
            **_mcp_tool_details_for_analytics(tool.name, mcp_server_type, mcp_server_base_url),
        })

        # Enrich tool_parameters with git commit ID
        if (
            _is_tool_details_logging_enabled()
            and tool.name in (BASH, POWERSHELL)
            and isinstance(processed_input, dict)
            and "command" in processed_input
            and isinstance(processed_input.get("command"), str)
            and "git" in processed_input["command"]
            and "commit" in processed_input["command"]
            and isinstance(result, dict)
            and isinstance(result.get("data"), dict)
            and "stdout" in result["data"]
        ):
            git_commit_id = _parse_git_commit_id(str(result["data"]["stdout"]))
            if git_commit_id:
                tool_parameters["git_commit_id"] = git_commit_id

        # Log tool_result OTel event
        mcp_server_scope = _get_mcp_server_scope_from_tool_name(tool.name) if _is_mcp_tool(tool) else None
        _log_otel_event("tool_result", {
            "tool_name": _sanitize_tool_name(tool.name),
            "success": "true",
            "duration_ms": str(duration_ms),
            **({"tool_parameters": _json_stringify(tool_parameters)} if tool_parameters else {}),
            **({"tool_input": telemetry_tool_input} if telemetry_tool_input else {}),
            "tool_result_size_bytes": str(tool_result_size_bytes),
            **({"decision_source": decision_info.source, "decision_type": decision_info.decision}
               if decision_info else {}),
            **({"mcp_server_scope": mcp_server_scope} if mcp_server_scope else {}),
        })

        # ---------- Step 9: Run PostToolUse hooks ----------
        tool_output = result.get("data") if isinstance(result, dict) else result
        hook_results: List[MessageUpdateLazy] = []
        tool_context_modifier = result.get("context_modifier") if isinstance(result, dict) else getattr(result, "context_modifier", None)
        mcp_meta = result.get("mcp_meta") if isinstance(result, dict) else getattr(result, "mcp_meta", None)

        async def add_tool_result(
            tool_use_result: Any,
            pre_mapped_block: Optional[dict] = None,
        ) -> None:
            """Build and append the tool result message (and optional feedback)."""
            if pre_mapped_block is not None:
                tool_result_block = await _process_pre_mapped_tool_result_block(
                    pre_mapped_block,
                    tool.name,
                    getattr(tool, "max_result_size_chars", 10_000_000),
                )
            else:
                tool_result_block = await _process_tool_result_block(tool, tool_use_result, tool_use_id)

            content_blocks: list = [tool_result_block]

            # Add accept feedback if user provided feedback when approving
            accept_feedback = getattr(permission_decision, "accept_feedback", None)
            if accept_feedback:
                content_blocks.append({"type": "text", "text": accept_feedback})

            # Add content blocks (e.g. pasted images) from permission decision
            allow_content_blocks = getattr(permission_decision, "content_blocks", None)
            if allow_content_blocks:
                content_blocks.extend(allow_content_blocks)

            # Generate sequential imagePasteIds
            allow_image_ids: Optional[list] = None
            if allow_content_blocks:
                img_count = _count(
                    allow_content_blocks,
                    lambda b: (b.get("type") if isinstance(b, dict) else getattr(b, "type", "")) == "image",
                )
                if img_count > 0:
                    messages_list = getattr(tool_use_context, "messages", []) or []
                    start_id = _get_next_image_paste_id(messages_list)
                    allow_image_ids = list(range(start_id, start_id + img_count))

            agent_id = getattr(tool_use_context, "agent_id", None)
            preserve = getattr(tool_use_context, "preserve_tool_use_results", False)
            resulting_messages.append(
                MessageUpdateLazy(
                    message=_create_user_message_raw(
                        content=content_blocks,
                        image_paste_ids=allow_image_ids,
                        tool_use_result=(
                            None if (agent_id and not preserve) else tool_use_result
                        ),
                        mcp_meta=None if agent_id else mcp_meta,
                        source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
                    ),
                    context_modifier=MessageUpdateContextModifier(
                        tool_use_id=tool_use_id,
                        modify_context=tool_context_modifier,
                    ) if tool_context_modifier else None,
                )
            )

        # Non-MCP tools: add result before post-hooks
        if not _is_mcp_tool(tool):
            await add_tool_result(tool_output, mapped_tool_result_block)

        post_tool_hook_infos: List[StopHookInfo] = []
        post_tool_hook_start = _now_ms()
        async for hook_result in _run_post_tool_use_hooks(
            tool_use_context,
            tool,
            tool_use_id,
            message_id,
            processed_input,
            tool_output,
            request_id,
            mcp_server_type,
            mcp_server_base_url,
        ):
            if isinstance(hook_result, dict) and "updated_mcp_tool_output" in hook_result:
                if _is_mcp_tool(tool):
                    tool_output = hook_result["updated_mcp_tool_output"]
            elif hasattr(hook_result, "updated_mcp_tool_output"):
                if _is_mcp_tool(tool):
                    tool_output = hook_result.updated_mcp_tool_output
            elif _is_mcp_tool(tool):
                hook_results.append(
                    hook_result if isinstance(hook_result, MessageUpdateLazy)
                    else MessageUpdateLazy(message=hook_result)
                )
                # Extract hook timing info
                inner_msg = getattr(hook_result, "message", None) or (hook_result.get("message") if isinstance(hook_result, dict) else None)
                if inner_msg is not None:
                    att = (
                        inner_msg.get("attachment") if isinstance(inner_msg, dict)
                        else getattr(inner_msg, "attachment", None)
                    )
                    if att is not None:
                        cmd = att.get("command") if isinstance(att, dict) else getattr(att, "command", None)
                        dur = att.get("durationMs") if isinstance(att, dict) else getattr(att, "duration_ms", None)
                        if cmd is not None and dur is not None:
                            post_tool_hook_infos.append(StopHookInfo(command=cmd, duration_ms=dur))
            else:
                resulting_messages.append(
                    hook_result if isinstance(hook_result, MessageUpdateLazy)
                    else MessageUpdateLazy(message=hook_result)
                )
                # Extract hook timing info for non-MCP
                inner_msg = getattr(hook_result, "message", None) or (hook_result.get("message") if isinstance(hook_result, dict) else None)
                if inner_msg is not None:
                    att = (
                        inner_msg.get("attachment") if isinstance(inner_msg, dict)
                        else getattr(inner_msg, "attachment", None)
                    )
                    if att is not None:
                        cmd = att.get("command") if isinstance(att, dict) else getattr(att, "command", None)
                        dur = att.get("durationMs") if isinstance(att, dict) else getattr(att, "duration_ms", None)
                        if cmd is not None and dur is not None:
                            post_tool_hook_infos.append(StopHookInfo(command=cmd, duration_ms=dur))

        post_tool_hook_duration_ms = _now_ms() - post_tool_hook_start
        if post_tool_hook_duration_ms >= _SLOW_PHASE_LOG_THRESHOLD_MS:
            _log_for_debugging(
                f"Slow PostToolUse hooks: {post_tool_hook_duration_ms}ms for {tool.name} "
                f"({len(post_tool_hook_infos)} hooks)",
                {"level": "info"},
            )

        # MCP tools: add result after post-hooks (may have updatedMCPToolOutput)
        if _is_mcp_tool(tool):
            await add_tool_result(tool_output)

        # Show PostToolUse hook timing inline below tool result when > 500ms.
        if os.environ.get("USER_TYPE") == "ant" and post_tool_hook_infos:
            if post_tool_hook_duration_ms > HOOK_TIMING_DISPLAY_THRESHOLD_MS:
                resulting_messages.append(
                    MessageUpdateLazy(
                        message=_create_stop_hook_summary_message(
                            len(post_tool_hook_infos),
                            post_tool_hook_infos,
                            [],
                            False,
                            None,
                            False,
                            "suggestion",
                            None,
                            "PostToolUse",
                            post_tool_hook_duration_ms,
                        )
                    )
                )

        # Append any new messages generated by the tool
        new_messages = result.get("new_messages") if isinstance(result, dict) else getattr(result, "new_messages", None)
        if new_messages:
            for msg in new_messages:
                resulting_messages.append(
                    msg if isinstance(msg, MessageUpdateLazy) else MessageUpdateLazy(message=msg)
                )

        # If hook indicated to prevent continuation after successful execution
        if should_prevent_continuation:
            resulting_messages.append(
                MessageUpdateLazy(
                    message=_create_attachment_message(
                        type="hook_stopped_continuation",
                        message=stop_reason or "Execution stopped by hook",
                        hook_name=f"PreToolUse:{tool.name}",
                        tool_use_id=tool_use_id,
                        hook_event="PreToolUse",
                    )
                )
            )

        # Append remaining MCP hook results
        for hr in hook_results:
            resulting_messages.append(hr)

        return resulting_messages

    except Exception as error:
        duration_ms = _now_ms() - start_time
        _add_to_tool_duration(duration_ms)

        _end_tool_execution_span({
            "success": False,
            "error": str(error),
        })
        _end_tool_span()

        # Handle MCP auth errors — update client status to 'needs-auth'
        try:
            from claude_code.services.mcp.client import McpAuthError
            if isinstance(error, McpAuthError):
                set_app_state_fn = getattr(tool_use_context, "set_app_state", None)
                if set_app_state_fn and callable(set_app_state_fn):
                    server_name = error.server_name

                    def _update_mcp_state(prev_state: Any) -> Any:
                        clients = getattr(prev_state, "mcp", {})
                        client_list = clients.get("clients", []) if isinstance(clients, dict) else getattr(clients, "clients", [])
                        idx = next(
                            (i for i, c in enumerate(client_list)
                             if (c.get("name") if isinstance(c, dict) else getattr(c, "name", "")) == server_name),
                            -1,
                        )
                        if idx == -1:
                            return prev_state
                        existing = client_list[idx]
                        conn_type = existing.get("type") if isinstance(existing, dict) else getattr(existing, "type", "")
                        if conn_type != "connected":
                            return prev_state
                        updated_clients = list(client_list)
                        if isinstance(existing, dict):
                            updated_clients[idx] = {**existing, "type": "needs-auth"}
                        else:
                            updated_clients[idx] = type(existing)(
                                name=server_name,
                                type="needs-auth",
                                config=getattr(existing, "config", {}),
                            )
                        # Build updated state
                        if isinstance(prev_state, dict):
                            return {**prev_state, "mcp": {**prev_state.get("mcp", {}), "clients": updated_clients}}
                        return prev_state

                    set_app_state_fn(_update_mcp_state)
        except ImportError:
            pass

        try:
            from claude_code.utils.errors import AbortError, ShellError
            is_abort = isinstance(error, AbortError)
            is_shell_err = isinstance(error, ShellError)
        except ImportError:
            is_abort = False
            is_shell_err = False

        if not is_abort:
            _log_for_debugging(
                f"{tool.name} tool error ({duration_ms}ms): {str(error)[:200]}"
            )
            if not is_shell_err:
                _log_error(error)

            _log_event("tengu_tool_use_error", {
                "messageID": message_id,
                "toolName": _sanitize_tool_name(tool.name),
                "error": classify_tool_error(error),
                "isMcp": getattr(tool, "is_mcp", False) or False,
                **({"queryChainId": tool_use_context.query_tracking.chain_id}
                   if getattr(tool_use_context, "query_tracking", None) else {}),
                **({"queryDepth": tool_use_context.query_tracking.depth}
                   if getattr(tool_use_context, "query_tracking", None) else {}),
                **({"mcpServerType": mcp_server_type} if mcp_server_type else {}),
                **({"mcpServerBaseUrl": mcp_server_base_url} if mcp_server_base_url else {}),
                **({"requestId": request_id} if request_id else {}),
                **_mcp_tool_details_for_analytics(tool.name, mcp_server_type, mcp_server_base_url),
            })

            mcp_server_scope = _get_mcp_server_scope_from_tool_name(tool.name) if _is_mcp_tool(tool) else None
            _log_otel_event("tool_result", {
                "tool_name": _sanitize_tool_name(tool.name),
                "use_id": tool_use_id,
                "success": "false",
                "duration_ms": str(duration_ms),
                "error": str(error),
                **({"tool_parameters": _json_stringify(tool_parameters)} if tool_parameters else {}),
                **({"tool_input": telemetry_tool_input} if telemetry_tool_input else {}),
                **({"decision_source": decision_info.source, "decision_type": decision_info.decision}
                   if decision_info else {}),
                **({"mcp_server_scope": mcp_server_scope} if mcp_server_scope else {}),
            })

        content = _format_error(error)
        is_interrupt = is_abort

        hook_messages: List[MessageUpdateLazy] = []
        async for hr in _run_post_tool_use_failure_hooks(
            tool_use_context,
            tool,
            tool_use_id,
            message_id,
            processed_input,
            content,
            is_interrupt,
            request_id,
            mcp_server_type,
            mcp_server_base_url,
        ):
            hook_messages.append(
                hr if isinstance(hr, MessageUpdateLazy) else MessageUpdateLazy(message=hr)
            )

        # Build mcp_meta for error message
        mcp_meta_for_error = None
        try:
            from claude_code.services.mcp.client import McpToolCallError
            if isinstance(error, McpToolCallError):
                mcp_meta_for_error = getattr(error, "mcp_meta", None)
        except ImportError:
            pass

        agent_id = getattr(tool_use_context, "agent_id", None)
        return [
            MessageUpdateLazy(
                message=_create_user_message_raw(
                    content=[{
                        "type": "tool_result",
                        "content": content,
                        "is_error": True,
                        "tool_use_id": tool_use_id,
                    }],
                    tool_use_result=f"Error: {content}",
                    mcp_meta=None if agent_id else mcp_meta_for_error,
                    source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
                )
            ),
            *hook_messages,
        ]

    finally:
        _stop_session_activity("tool_exec")
        # Clean up decision info after logging
        if tool_decisions and tool_use_id in tool_decisions:
            del tool_decisions[tool_use_id]


# ---------------------------------------------------------------------------
# streamedCheckPermissionsAndCallTool
# ---------------------------------------------------------------------------

def streamed_check_permissions_and_call_tool(
    tool: Any,
    tool_use_id: str,
    input_data: dict,
    tool_use_context: Any,
    can_use_tool: Any,
    assistant_message: Any,
    message_id: str,
    request_id: Optional[str],
    mcp_server_type: McpServerType,
    mcp_server_base_url: Optional[str],
) -> "AsyncGenerator[MessageUpdateLazy, None]":
    """
    Wraps checkPermissionsAndCallTool in a stream so that progress events
    and final results come from a single AsyncIterable.

    Mirrors TS streamedCheckPermissionsAndCallTool().
    """
    stream: Stream = Stream()

    def _on_progress(progress: Any) -> None:
        tool_use_id_ = (
            progress.get("toolUseID") if isinstance(progress, dict)
            else getattr(progress, "tool_use_id", tool_use_id)
        )
        parent_id = (
            progress.get("parentToolUseID") if isinstance(progress, dict)
            else getattr(progress, "parent_tool_use_id", tool_use_id)
        ) or tool_use_id
        data = progress.get("data") if isinstance(progress, dict) else getattr(progress, "data", None)

        # Log analytics for progress
        _log_event("tengu_tool_use_progress", {
            "messageID": message_id,
            "toolName": _sanitize_tool_name(tool.name),
            "isMcp": getattr(tool, "is_mcp", False) or False,
            **({"mcpServerType": mcp_server_type} if mcp_server_type else {}),
            **({"mcpServerBaseUrl": mcp_server_base_url} if mcp_server_base_url else {}),
            **({"requestId": request_id} if request_id else {}),
            **({"queryChainId": tool_use_context.query_tracking.chain_id}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **({"queryDepth": tool_use_context.query_tracking.depth}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **_mcp_tool_details_for_analytics(tool.name, mcp_server_type, mcp_server_base_url),
        })

        stream.enqueue(
            MessageUpdateLazy(
                message=_create_progress_message(
                    tool_use_id=tool_use_id_,
                    parent_tool_use_id=parent_id,
                    data=data,
                )
            )
        )

    async def _run() -> None:
        try:
            results = await check_permissions_and_call_tool(
                tool,
                tool_use_id,
                input_data,
                tool_use_context,
                can_use_tool,
                assistant_message,
                message_id,
                request_id,
                mcp_server_type,
                mcp_server_base_url,
                _on_progress,
            )
            for r in results:
                stream.enqueue(r)
        except Exception as exc:
            stream.error(exc)
        finally:
            stream.done()

    asyncio.ensure_future(_run())
    return stream


# ---------------------------------------------------------------------------
# Public: runToolUse
# ---------------------------------------------------------------------------

async def run_tool_use(
    tool_use: Any,
    assistant_message: Any,
    can_use_tool: Any,
    tool_use_context: Any,
) -> AsyncGenerator[MessageUpdateLazy, None]:
    """
    Execute a single tool-use block from the assistant message.

    Mirrors TS: export async function* runToolUse(...).

    Yields MessageUpdateLazy objects for every message to append
    (progress, result, permission-denied, error, etc.).
    """
    tool_name = (
        tool_use.get("name") if isinstance(tool_use, dict)
        else getattr(tool_use, "name", "unknown")
    )

    # First: find in available tools (what the model sees)
    tools_list = getattr(getattr(tool_use_context, "options", None), "tools", []) or []
    tool = _find_tool_by_name(tools_list, tool_name)

    # If not found, check if it's a deprecated tool being called by alias
    if not tool:
        fallback = _find_tool_by_name(_get_all_base_tools(), tool_name)
        aliases = getattr(fallback, "aliases", []) if fallback else []
        if fallback and tool_name in aliases:
            tool = fallback

    # Extract IDs
    mcp_clients = getattr(getattr(tool_use_context, "options", None), "mcp_clients", []) or []
    message_id = (
        getattr(getattr(assistant_message, "message", assistant_message), "id", "")
        or (assistant_message.get("message", {}).get("id", "") if isinstance(assistant_message, dict) else "")
    )
    request_id = getattr(assistant_message, "request_id", None) or (
        assistant_message.get("requestId") if isinstance(assistant_message, dict) else None
    )
    tool_use_id = (
        tool_use.get("id") if isinstance(tool_use, dict)
        else getattr(tool_use, "id", "")
    ) or ""

    mcp_server_type = _get_mcp_server_type(tool_name, mcp_clients)
    mcp_server_base_url = _get_mcp_server_base_url(tool_name, mcp_clients)

    # ---------- Unknown tool ----------
    if tool is None:
        sanitized = _sanitize_tool_name(tool_name)
        _log_for_debugging(f"Unknown tool {tool_name}: {tool_use_id}")
        _log_event("tengu_tool_use_error", {
            "error": f"No such tool available: {sanitized}",
            "toolName": sanitized,
            "toolUseID": tool_use_id,
            "isMcp": tool_name.startswith("mcp__"),
            **({"mcpServerType": mcp_server_type} if mcp_server_type else {}),
            **({"mcpServerBaseUrl": mcp_server_base_url} if mcp_server_base_url else {}),
            **({"requestId": request_id} if request_id else {}),
            **({"queryChainId": tool_use_context.query_tracking.chain_id}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **({"queryDepth": tool_use_context.query_tracking.depth}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **_mcp_tool_details_for_analytics(tool_name, mcp_server_type, mcp_server_base_url),
        })
        yield MessageUpdateLazy(
            message=_create_user_message_raw(
                content=[{
                    "type": "tool_result",
                    "content": f"<tool_use_error>Error: No such tool available: {tool_name}</tool_use_error>",
                    "is_error": True,
                    "tool_use_id": tool_use_id,
                }],
                tool_use_result=f"Error: No such tool available: {tool_name}",
                source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
            )
        )
        return

    tool_input = (
        tool_use.get("input") if isinstance(tool_use, dict)
        else getattr(tool_use, "input", {})
    ) or {}

    # ---------- Abort-before-start check ----------
    abort_ctrl = getattr(tool_use_context, "abort_controller", None)
    signal_aborted = getattr(abort_ctrl, "signal", None)
    is_aborted = (
        getattr(signal_aborted, "aborted", False)
        if signal_aborted is not None else False
    )

    if is_aborted:
        _log_event("tengu_tool_use_cancelled", {
            "toolName": _sanitize_tool_name(tool.name),
            "toolUseID": tool_use_id,
            "isMcp": getattr(tool, "is_mcp", False) or False,
            **({"mcpServerType": mcp_server_type} if mcp_server_type else {}),
            **({"mcpServerBaseUrl": mcp_server_base_url} if mcp_server_base_url else {}),
            **({"requestId": request_id} if request_id else {}),
            **({"queryChainId": tool_use_context.query_tracking.chain_id}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **({"queryDepth": tool_use_context.query_tracking.depth}
               if getattr(tool_use_context, "query_tracking", None) else {}),
            **_mcp_tool_details_for_analytics(tool.name, mcp_server_type, mcp_server_base_url),
        })
        cancel_msg = _get_cancel_message()
        content = _create_tool_result_stop_message(tool_use_id)
        if isinstance(content, dict):
            content["content"] = _with_memory_correction_hint(cancel_msg)
        yield MessageUpdateLazy(
            message=_create_user_message_raw(
                content=[content],
                tool_use_result=cancel_msg,
                source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
            )
        )
        return

    # ---------- Delegate to the streaming pipeline ----------
    try:
        async for update in streamed_check_permissions_and_call_tool(
            tool,
            tool_use_id,
            tool_input,
            tool_use_context,
            can_use_tool,
            assistant_message,
            message_id,
            request_id,
            mcp_server_type,
            mcp_server_base_url,
        ):
            yield update
    except Exception as error:
        _log_error(error)
        err_msg = str(error)
        detailed_error = f"Error calling tool ({tool.name}): {err_msg}"
        yield MessageUpdateLazy(
            message=_create_user_message_raw(
                content=[{
                    "type": "tool_result",
                    "content": f"<tool_use_error>{detailed_error}</tool_use_error>",
                    "is_error": True,
                    "tool_use_id": tool_use_id,
                }],
                tool_use_result=detailed_error,
                source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
            )
        )


# ---------------------------------------------------------------------------
# Utility: wall-clock time in milliseconds
# ---------------------------------------------------------------------------

def _now_ms() -> int:
    return int(time.monotonic() * 1000)

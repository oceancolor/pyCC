"""
Tool execution engine.
Ported from services/tools/toolExecution.ts (1745 lines).

Handles permission checking, hook running, and actual tool call dispatch.

原始 TS: services/tools/toolExecution.ts
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple

from ...utils.log import log_error
from ...utils.debug import log_for_debugging

# Thresholds
HOOK_TIMING_DISPLAY_THRESHOLD_MS = 500
_SLOW_PHASE_LOG_THRESHOLD_MS = 2000


# ---------------------------------------------------------------------------
# Error classifier
# ---------------------------------------------------------------------------


def classify_tool_error(error: Any) -> str:
    """Classify a tool execution error into a telemetry-safe string."""
    if error is None:
        return "UnknownError"
    if hasattr(error, "telemetry_message"):
        return str(error.telemetry_message)[:200]
    if isinstance(error, OSError):
        errno_code = _get_errno_code(error)
        if errno_code:
            return f"Error:{errno_code}"
    if isinstance(error, Exception):
        name = getattr(error, "name", None) or type(error).__name__
        if name and name != "Error" and len(name) > 3:
            return name[:60]
        return "Error"
    return "UnknownError"


def _get_errno_code(error: Any) -> Optional[str]:
    """Extract errno code from an OSError."""
    import errno as _errno
    if isinstance(error, OSError) and error.errno is not None:
        return _errno.errorcode.get(error.errno, f"E{error.errno}")
    return None


# ---------------------------------------------------------------------------
# Source / OTel helpers (stubs — real analytics not ported)
# ---------------------------------------------------------------------------


def _log_event(event: str, data: Dict[str, Any] = {}) -> None:
    """Stub for analytics logEvent."""
    try:
        from ...services.analytics import log_event  # type: ignore
        log_event(event, data)
    except (ImportError, Exception):
        pass


def _sanitize_tool_name(name: str) -> str:
    """Stub for sanitizeToolNameForAnalytics."""
    try:
        from ...services.analytics.metadata import sanitize_tool_name_for_analytics  # type: ignore
        return sanitize_tool_name_for_analytics(name)
    except (ImportError, Exception):
        return name[:100]


def _find_tool_by_name(tools: Any, name: str) -> Optional[Any]:
    """Find a tool by name from a tools collection."""
    try:
        from ...tool import find_tool_by_name  # type: ignore
        return find_tool_by_name(tools, name)
    except (ImportError, Exception):
        pass

    if isinstance(tools, (list, tuple)):
        for t in tools:
            if getattr(t, "name", None) == name:
                return t
            aliases = getattr(t, "aliases", None) or []
            if name in aliases:
                return t
    return None


def _is_mcp_tool(tool: Any) -> bool:
    """Check if a tool is an MCP tool."""
    try:
        from ...services.mcp.utils import is_mcp_tool  # type: ignore
        return is_mcp_tool(tool)
    except (ImportError, Exception):
        return getattr(tool, "is_mcp", False) or getattr(tool, "isMcp", False)


def _get_next_image_paste_id(messages: List[Any]) -> int:
    """Get the next sequential imagePasteId."""
    max_id = 0
    for msg in messages:
        if getattr(msg, "type", None) == "user" and hasattr(msg, "message"):
            ids = getattr(msg.message, "image_paste_ids", None) or []
            for i in ids:
                if i > max_id:
                    max_id = i
    return max_id + 1


def _create_user_message(**kwargs: Any) -> Any:
    from ...utils.messages import create_user_message  # type: ignore
    return create_user_message(**kwargs)


def _create_progress_message(**kwargs: Any) -> Any:
    from ...utils.messages import create_progress_message  # type: ignore
    return create_progress_message(**kwargs)


def _create_tool_result_stop_message(tool_use_id: str) -> Any:
    from ...utils.messages import create_tool_result_stop_message  # type: ignore
    return create_tool_result_stop_message(tool_use_id)


def _create_attachment_message(attachment: Any) -> Any:
    from ...utils.attachments import create_attachment_message  # type: ignore
    return create_attachment_message(attachment)


# ---------------------------------------------------------------------------
# MessageUpdateLazy type
# ---------------------------------------------------------------------------


class MessageUpdateLazy:
    """Lazy message update wrapper."""

    def __init__(
        self,
        message: Any,
        context_modifier: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.message = message
        self.context_modifier = context_modifier


# ---------------------------------------------------------------------------
# MCP helpers
# ---------------------------------------------------------------------------


def _get_mcp_server_type(
    tool_name: str,
    mcp_clients: List[Any],
) -> Optional[str]:
    """Get the MCP server transport type for a tool."""
    try:
        from ...services.mcp.utils import get_mcp_server_type  # type: ignore
        return get_mcp_server_type(tool_name, mcp_clients)
    except (ImportError, Exception):
        return None


def _get_mcp_server_base_url(
    tool_name: str,
    mcp_clients: List[Any],
) -> Optional[str]:
    """Get the MCP server base URL for a tool."""
    try:
        from ...services.mcp.utils import get_mcp_server_base_url_from_tool_name  # type: ignore
        return get_mcp_server_base_url_from_tool_name(tool_name, mcp_clients)
    except (ImportError, Exception):
        return None


# ---------------------------------------------------------------------------
# Main runToolUse
# ---------------------------------------------------------------------------


async def run_tool_use(
    tool_use: Any,
    assistant_message: Any,
    can_use_tool: Any,
    tool_use_context: Any,
) -> AsyncGenerator[MessageUpdateLazy, None]:
    """Execute a single tool use block and yield message updates."""
    tool_name = getattr(tool_use, "name", "") or tool_use.get("name", "") if isinstance(tool_use, dict) else ""
    if not tool_name and hasattr(tool_use, "name"):
        tool_name = tool_use.name

    options = getattr(tool_use_context, "options", None) or {}
    tools = getattr(options, "tools", []) if hasattr(options, "tools") else options.get("tools", [])
    mcp_clients = (
        getattr(options, "mcp_clients", []) if hasattr(options, "mcp_clients")
        else options.get("mcpClients", [])
    )

    # Find tool
    tool = _find_tool_by_name(tools, tool_name)
    if not tool:
        # Try fallback with aliases
        try:
            from ...tools import get_all_base_tools  # type: ignore
            fallback = _find_tool_by_name(get_all_base_tools(), tool_name)
            aliases = getattr(fallback, "aliases", None) or []
            if fallback and tool_name in aliases:
                tool = fallback
        except (ImportError, Exception):
            pass

    tool_use_id = getattr(tool_use, "id", "") or (tool_use.get("id", "") if isinstance(tool_use, dict) else "")
    msg_id = getattr(getattr(assistant_message, "message", None), "id", "") or ""
    request_id = getattr(assistant_message, "request_id", None)
    mcp_server_type = _get_mcp_server_type(tool_name, mcp_clients)
    mcp_server_base_url = _get_mcp_server_base_url(tool_name, mcp_clients)

    if not tool:
        log_for_debugging(f"Unknown tool {tool_name}: {tool_use_id}")
        _log_event("tengu_tool_use_error", {
            "error": f"No such tool available: {_sanitize_tool_name(tool_name)}",
            "toolName": _sanitize_tool_name(tool_name),
            "toolUseID": tool_use_id,
            "isMcp": tool_name.startswith("mcp__"),
        })
        msg = _create_user_message(
            content=[{
                "type": "tool_result",
                "content": f"<tool_use_error>Error: No such tool available: {tool_name}</tool_use_error>",
                "is_error": True,
                "tool_use_id": tool_use_id,
            }],
            tool_use_result=f"Error: No such tool available: {tool_name}",
            source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
        )
        yield MessageUpdateLazy(message=msg)
        return

    tool_input = getattr(tool_use, "input", {})
    if isinstance(tool_use, dict):
        tool_input = tool_use.get("input", {})

    try:
        # Check abort
        abort_ctrl = getattr(tool_use_context, "abort_controller", None)
        abort_signal = getattr(abort_ctrl, "signal", abort_ctrl) if abort_ctrl else None
        if abort_signal and getattr(abort_signal, "aborted", False):
            _log_event("tengu_tool_use_cancelled", {"toolName": _sanitize_tool_name(tool_name), "toolUseID": tool_use_id})
            content = _create_tool_result_stop_message(tool_use_id)
            try:
                from ...utils.messages import with_memory_correction_hint, CANCEL_MESSAGE  # type: ignore
                if hasattr(content, "content"):
                    content.content = with_memory_correction_hint(CANCEL_MESSAGE)
            except (ImportError, Exception):
                pass
            msg = _create_user_message(
                content=[content],
                tool_use_result="Cancelled",
                source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
            )
            yield MessageUpdateLazy(message=msg)
            return

        # Stream through streamed_check_permissions_and_call_tool
        async for update in _streamed_check_permissions_and_call_tool(
            tool=tool,
            tool_use_id=tool_use_id,
            input=tool_input,
            tool_use_context=tool_use_context,
            can_use_tool=can_use_tool,
            assistant_message=assistant_message,
            message_id=msg_id,
            request_id=request_id,
            mcp_server_type=mcp_server_type,
            mcp_server_base_url=mcp_server_base_url,
        ):
            yield update

    except Exception as e:
        log_error(e)
        err_msg = str(e)
        tool_info = f" ({tool.name})" if tool else ""
        detailed_error = f"Error calling tool{tool_info}: {err_msg}"
        msg = _create_user_message(
            content=[{
                "type": "tool_result",
                "content": f"<tool_use_error>{detailed_error}</tool_use_error>",
                "is_error": True,
                "tool_use_id": tool_use_id,
            }],
            tool_use_result=detailed_error,
            source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
        )
        yield MessageUpdateLazy(message=msg)


async def _streamed_check_permissions_and_call_tool(
    tool: Any,
    tool_use_id: str,
    input: Dict[str, Any],
    tool_use_context: Any,
    can_use_tool: Any,
    assistant_message: Any,
    message_id: str,
    request_id: Optional[str],
    mcp_server_type: Optional[str],
    mcp_server_base_url: Optional[str],
) -> AsyncGenerator[MessageUpdateLazy, None]:
    """Stream permission checks and tool execution as message updates."""
    try:
        from ...utils.stream import AsyncStream  # type: ignore
        stream: Any = AsyncStream()
        use_stream = True
    except (ImportError, Exception):
        use_stream = False
        stream = None

    if use_stream and stream:
        async def _run() -> None:
            try:
                results = await _check_permissions_and_call_tool(
                    tool=tool,
                    tool_use_id=tool_use_id,
                    input=input,
                    tool_use_context=tool_use_context,
                    can_use_tool=can_use_tool,
                    assistant_message=assistant_message,
                    message_id=message_id,
                    request_id=request_id,
                    mcp_server_type=mcp_server_type,
                    mcp_server_base_url=mcp_server_base_url,
                    on_tool_progress=lambda p: stream.enqueue(
                        MessageUpdateLazy(
                            message=_create_progress_message(
                                tool_use_id=getattr(p, "tool_use_id", tool_use_id),
                                parent_tool_use_id=tool_use_id,
                                data=getattr(p, "data", p),
                            )
                        )
                    ),
                )
                for r in results:
                    stream.enqueue(r)
            except Exception as e:
                stream.error(e)
            finally:
                stream.done()

        asyncio.ensure_future(_run())
        async for item in stream:
            yield item
    else:
        # Fallback: collect all at once
        results = await _check_permissions_and_call_tool(
            tool=tool,
            tool_use_id=tool_use_id,
            input=input,
            tool_use_context=tool_use_context,
            can_use_tool=can_use_tool,
            assistant_message=assistant_message,
            message_id=message_id,
            request_id=request_id,
            mcp_server_type=mcp_server_type,
            mcp_server_base_url=mcp_server_base_url,
            on_tool_progress=lambda p: None,
        )
        for r in results:
            yield r


async def _check_permissions_and_call_tool(
    tool: Any,
    tool_use_id: str,
    input: Dict[str, Any],
    tool_use_context: Any,
    can_use_tool: Any,
    assistant_message: Any,
    message_id: str,
    request_id: Optional[str],
    mcp_server_type: Optional[str],
    mcp_server_base_url: Optional[str],
    on_tool_progress: Any,
) -> List[MessageUpdateLazy]:
    """Core permission check and tool call logic."""
    resulting_messages: List[MessageUpdateLazy] = []

    # Validate input with schema
    input_schema = getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", None)
    parsed_input = input
    if input_schema:
        try:
            result = input_schema.safe_parse(input) if hasattr(input_schema, "safe_parse") else None
            if result is not None:
                if not result.success:
                    try:
                        from ...utils.tool_errors import format_zod_validation_error  # type: ignore
                        error_content = format_zod_validation_error(tool.name, result.error)
                    except (ImportError, Exception):
                        error_content = str(result.error)
                    _log_event("tengu_tool_use_error", {
                        "error": "InputValidationError",
                        "toolName": _sanitize_tool_name(tool.name),
                    })
                    msg = _create_user_message(
                        content=[{
                            "type": "tool_result",
                            "content": f"<tool_use_error>InputValidationError: {error_content}</tool_use_error>",
                            "is_error": True,
                            "tool_use_id": tool_use_id,
                        }],
                        tool_use_result=f"InputValidationError: {error_content}",
                        source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
                    )
                    return [MessageUpdateLazy(message=msg)]
                else:
                    parsed_input = result.data
        except Exception:
            pass

    # Validate input values
    validate_fn = getattr(tool, "validate_input", None) or getattr(tool, "validateInput", None)
    if validate_fn and callable(validate_fn):
        try:
            is_valid_call = validate_fn(parsed_input, tool_use_context)
            if asyncio.iscoroutine(is_valid_call):
                is_valid_call = await is_valid_call
            if is_valid_call and getattr(is_valid_call, "result", True) is False:
                err_msg = getattr(is_valid_call, "message", "Validation failed")
                msg = _create_user_message(
                    content=[{
                        "type": "tool_result",
                        "content": f"<tool_use_error>{err_msg}</tool_use_error>",
                        "is_error": True,
                        "tool_use_id": tool_use_id,
                    }],
                    tool_use_result=f"Error: {err_msg}",
                    source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
                )
                return [MessageUpdateLazy(message=msg)]
        except Exception:
            pass

    call_input = parsed_input
    processed_input = parsed_input
    should_prevent_continuation = False
    stop_reason: Optional[str] = None
    hook_permission_result = None
    pre_tool_hook_infos: List[Any] = []
    pre_tool_hook_start = time.monotonic()

    # Run PreToolUse hooks
    from .tool_hooks import run_pre_tool_use_hooks
    async for result in run_pre_tool_use_hooks(
        tool_use_context=tool_use_context,
        tool=tool,
        processed_input=processed_input,
        tool_use_id=tool_use_id,
        message_id=message_id,
        request_id=request_id,
        mcp_server_type=mcp_server_type,
        mcp_server_base_url=mcp_server_base_url,
    ):
        result_type = result.get("type") if isinstance(result, dict) else getattr(result, "type", None)
        if result_type == "message":
            msg_wrapper = result.get("message") if isinstance(result, dict) else result.message
            inner_msg = msg_wrapper.get("message") if isinstance(msg_wrapper, dict) else getattr(msg_wrapper, "message", msg_wrapper)
            if getattr(inner_msg, "type", None) == "progress":
                on_tool_progress(inner_msg)
            else:
                resulting_messages.append(
                    MessageUpdateLazy(message=inner_msg)
                )
        elif result_type == "hookPermissionResult":
            hook_permission_result = result.get("hookPermissionResult") if isinstance(result, dict) else getattr(result, "hookPermissionResult", None)
        elif result_type == "hookUpdatedInput":
            updated = result.get("updatedInput") if isinstance(result, dict) else getattr(result, "updatedInput", None)
            if updated is not None:
                processed_input = updated
        elif result_type == "preventContinuation":
            should_prevent_continuation = result.get("shouldPreventContinuation", True) if isinstance(result, dict) else True
        elif result_type == "stopReason":
            stop_reason = result.get("stopReason") if isinstance(result, dict) else getattr(result, "stopReason", None)
        elif result_type == "additionalContext":
            msg_wrapper = result.get("message") if isinstance(result, dict) else result.message
            inner_msg = msg_wrapper.get("message") if isinstance(msg_wrapper, dict) else getattr(msg_wrapper, "message", msg_wrapper)
            resulting_messages.append(MessageUpdateLazy(message=inner_msg))
        elif result_type == "stop":
            pre_hook_dur = int((time.monotonic() - pre_tool_hook_start) * 1000)
            resulting_messages.append(
                MessageUpdateLazy(
                    message=_create_user_message(
                        content=[_create_tool_result_stop_message(tool_use_id)],
                        tool_use_result=f"Error: {stop_reason}",
                        source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
                    )
                )
            )
            return resulting_messages

    pre_tool_hook_duration_ms = int((time.monotonic() - pre_tool_hook_start) * 1000)
    if pre_tool_hook_duration_ms >= _SLOW_PHASE_LOG_THRESHOLD_MS:
        log_for_debugging(
            f"Slow PreToolUse hooks: {pre_tool_hook_duration_ms}ms for {getattr(tool, 'name', '?')}",
        )

    # Resolve permission decision
    from .tool_hooks import resolve_hook_permission_decision
    resolved = await resolve_hook_permission_decision(
        hook_permission_result=hook_permission_result,
        tool=tool,
        input=processed_input,
        tool_use_context=tool_use_context,
        can_use_tool=can_use_tool,
        assistant_message=assistant_message,
        tool_use_id=tool_use_id,
    )
    permission_decision = resolved["decision"]
    processed_input = resolved["input"]

    permission_behavior = getattr(permission_decision, "behavior", None)
    if isinstance(permission_decision, dict):
        permission_behavior = permission_decision.get("behavior")

    if permission_behavior != "allow":
        log_for_debugging(f"{getattr(tool, 'name', '?')} tool permission denied")
        _log_event("tengu_tool_use_can_use_tool_rejected", {
            "toolName": _sanitize_tool_name(getattr(tool, "name", "")),
        })

        # Get error message
        err_msg = (
            getattr(permission_decision, "message", None)
            if not isinstance(permission_decision, dict)
            else permission_decision.get("message")
        )
        if should_prevent_continuation and not err_msg:
            err_msg = f"Execution stopped by PreToolUse hook{f': {stop_reason}' if stop_reason else ''}"

        msg = _create_user_message(
            content=[{
                "type": "tool_result",
                "content": err_msg,
                "is_error": True,
                "tool_use_id": tool_use_id,
            }],
            tool_use_result=f"Error: {err_msg}",
            source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
        )
        resulting_messages.append(MessageUpdateLazy(message=msg))
        return resulting_messages

    _log_event("tengu_tool_use_can_use_tool_allowed", {
        "toolName": _sanitize_tool_name(getattr(tool, "name", "")),
    })

    # Use updated input from permission decision if provided
    updated_from_permission = (
        getattr(permission_decision, "updated_input", None)
        if not isinstance(permission_decision, dict)
        else permission_decision.get("updatedInput") or permission_decision.get("updated_input")
    )
    if updated_from_permission is not None:
        processed_input = updated_from_permission

    call_input = processed_input

    # Call the tool
    start_time = time.monotonic()
    try:
        try:
            from ...utils.session_activity import start_session_activity, stop_session_activity  # type: ignore
            start_session_activity("tool_exec")
        except (ImportError, Exception):
            pass

        call_fn = getattr(tool, "call", None)
        if call_fn is None:
            raise ValueError(f"Tool {getattr(tool, 'name', '?')} has no call method")

        # Build progress callback
        def _on_progress(progress: Any) -> None:
            on_tool_progress(progress)

        user_modified = (
            getattr(permission_decision, "user_modified", False)
            if not isinstance(permission_decision, dict)
            else permission_decision.get("userModified", False)
        )

        result = call_fn(
            call_input,
            {**{
                k: getattr(tool_use_context, k, None)
                for k in dir(tool_use_context)
                if not k.startswith("_")
            }, "tool_use_id": tool_use_id, "user_modified": user_modified or False},
            can_use_tool,
            assistant_message,
            _on_progress,
        )
        if asyncio.iscoroutine(result):
            result = await result

        duration_ms = int((time.monotonic() - start_time) * 1000)

        try:
            from ...bootstrap.state import add_to_tool_duration  # type: ignore
            add_to_tool_duration(duration_ms)
        except (ImportError, Exception):
            pass

        _log_event("tengu_tool_use_success", {
            "toolName": _sanitize_tool_name(getattr(tool, "name", "")),
            "durationMs": duration_ms,
        })

        # Map result to tool result block
        result_data = getattr(result, "data", result) if result else None
        tool_output = result_data

        map_fn = getattr(tool, "map_tool_result_to_tool_result_block_param", None)
        if map_fn is None:
            map_fn = getattr(tool, "mapToolResultToToolResultBlockParam", None)

        mapped_block = None
        if map_fn and callable(map_fn):
            try:
                mapped_block = map_fn(result_data, tool_use_id)
            except Exception:
                pass

        async def _add_tool_result(tool_use_result: Any, pre_mapped_block: Any = None) -> None:
            # Get the final tool result block
            if pre_mapped_block:
                try:
                    from ...utils.tool_result_storage import process_pre_mapped_tool_result_block  # type: ignore
                    tool_result_block = await process_pre_mapped_tool_result_block(
                        pre_mapped_block, getattr(tool, "name", ""), getattr(tool, "max_result_size_chars", None)
                    )
                except (ImportError, Exception):
                    tool_result_block = pre_mapped_block
            else:
                try:
                    from ...utils.tool_result_storage import process_tool_result_block  # type: ignore
                    tool_result_block = await process_tool_result_block(tool, tool_use_result, tool_use_id)
                except (ImportError, Exception):
                    content = str(tool_use_result) if tool_use_result is not None else ""
                    tool_result_block = {
                        "type": "tool_result",
                        "content": content,
                        "tool_use_id": tool_use_id,
                    }

            content_blocks: List[Any] = [tool_result_block]

            # Add accept feedback
            accept_feedback = (
                getattr(permission_decision, "accept_feedback", None)
                if not isinstance(permission_decision, dict)
                else permission_decision.get("acceptFeedback")
            )
            if accept_feedback:
                content_blocks.append({"type": "text", "text": accept_feedback})

            msg = _create_user_message(
                content=content_blocks,
                tool_use_result=(
                    tool_use_result
                    if not (getattr(tool_use_context, "agent_id", None) and
                            not getattr(tool_use_context, "preserve_tool_use_results", False))
                    else None
                ),
                source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
            )
            resulting_messages.append(MessageUpdateLazy(message=msg))

        # Add tool result (non-MCP first)
        is_mcp = _is_mcp_tool(tool)
        if not is_mcp:
            await _add_tool_result(tool_output, mapped_block)

        # Run PostToolUse hooks
        from .tool_hooks import run_post_tool_use_hooks
        post_hook_start = time.monotonic()
        post_tool_hook_infos: List[Any] = []
        hook_results: List[Any] = []

        async for hook_result in run_post_tool_use_hooks(
            tool_use_context=tool_use_context,
            tool=tool,
            tool_use_id=tool_use_id,
            message_id=message_id,
            tool_input=processed_input,
            tool_response=tool_output,
            request_id=request_id,
            mcp_server_type=mcp_server_type,
            mcp_server_base_url=mcp_server_base_url,
        ):
            updated_out = hook_result.get("updatedMCPToolOutput") if isinstance(hook_result, dict) else getattr(hook_result, "updated_mcp_tool_output", None)
            if updated_out is not None:
                if is_mcp:
                    tool_output = updated_out
            elif is_mcp:
                msg = hook_result.get("message") if isinstance(hook_result, dict) else getattr(hook_result, "message", None)
                if msg:
                    hook_results.append(MessageUpdateLazy(message=msg))
            else:
                msg = hook_result.get("message") if isinstance(hook_result, dict) else getattr(hook_result, "message", None)
                if msg:
                    resulting_messages.append(MessageUpdateLazy(message=msg))

        post_hook_dur = int((time.monotonic() - post_hook_start) * 1000)
        if post_hook_dur >= _SLOW_PHASE_LOG_THRESHOLD_MS:
            log_for_debugging(f"Slow PostToolUse hooks: {post_hook_dur}ms for {getattr(tool, 'name', '?')}")

        if is_mcp:
            await _add_tool_result(tool_output)

        # Handle hook stopped continuation
        if should_prevent_continuation:
            att = _create_attachment_message({
                "type": "hook_stopped_continuation",
                "message": stop_reason or "Execution stopped by hook",
                "hookName": f"PreToolUse:{getattr(tool, 'name', '?')}",
                "toolUseID": tool_use_id,
                "hookEvent": "PreToolUse",
            })
            resulting_messages.append(MessageUpdateLazy(message=att))

        # Add new messages from result
        new_messages = getattr(result, "new_messages", None) or (
            getattr(result, "newMessages", None) if hasattr(result, "newMessages") else None
        )
        if new_messages:
            for nm in new_messages:
                resulting_messages.append(MessageUpdateLazy(message=nm))

        # Yield remaining hook results
        for hr in hook_results:
            resulting_messages.append(hr)

        return resulting_messages

    except Exception as error:
        duration_ms = int((time.monotonic() - start_time) * 1000)
        try:
            from ...bootstrap.state import add_to_tool_duration  # type: ignore
            add_to_tool_duration(duration_ms)
        except (ImportError, Exception):
            pass

        is_abort = False
        try:
            from ...utils.errors import AbortError  # type: ignore
            is_abort = isinstance(error, AbortError)
        except (ImportError, Exception):
            pass

        if not is_abort:
            err_name = getattr(error, "name", type(error).__name__)
            log_for_debugging(
                f"{getattr(tool, 'name', '?')} tool error ({duration_ms}ms): {str(error)[:200]}"
            )
            is_shell_err = False
            try:
                from ...utils.errors import ShellError  # type: ignore
                is_shell_err = isinstance(error, ShellError)
            except (ImportError, Exception):
                pass
            if not is_shell_err:
                log_error(error)

        try:
            from ...utils.tool_errors import format_error  # type: ignore
            content = format_error(error)
        except (ImportError, Exception):
            content = str(error)

        is_interrupt = is_abort

        # Run PostToolUseFailure hooks
        hook_messages: List[MessageUpdateLazy] = []
        from .tool_hooks import run_post_tool_use_failure_hooks
        async for hook_result in run_post_tool_use_failure_hooks(
            tool_use_context=tool_use_context,
            tool=tool,
            tool_use_id=tool_use_id,
            message_id=message_id,
            processed_input=processed_input,
            error=content,
            is_interrupt=is_interrupt,
            request_id=request_id,
            mcp_server_type=mcp_server_type,
            mcp_server_base_url=mcp_server_base_url,
        ):
            msg = hook_result.get("message") if isinstance(hook_result, dict) else getattr(hook_result, "message", None)
            if msg:
                hook_messages.append(MessageUpdateLazy(message=msg))

        error_msg = _create_user_message(
            content=[{
                "type": "tool_result",
                "content": content,
                "is_error": True,
                "tool_use_id": tool_use_id,
            }],
            tool_use_result=f"Error: {content}",
            source_tool_assistant_uuid=getattr(assistant_message, "uuid", None),
        )
        return [MessageUpdateLazy(message=error_msg)] + hook_messages

    finally:
        try:
            from ...utils.session_activity import stop_session_activity  # type: ignore
            stop_session_activity("tool_exec")
        except (ImportError, Exception):
            pass

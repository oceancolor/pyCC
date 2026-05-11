"""
Tool hook runners (pre/post use, failure).
Ported from services/tools/toolHooks.ts (650 lines).

This module implements the hook dispatch logic for pre-tool-use,
post-tool-use, and post-tool-use-failure events.

原始 TS: services/tools/toolHooks.ts
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, AsyncGenerator, Dict, Optional, Union

from ...utils.log import log_error
from ...utils.debug import log_for_debugging


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

class PostToolUseHooksResult:
    """Result from a post-tool-use hook execution."""

    def __init__(
        self,
        message: Optional[Any] = None,
        updated_mcp_tool_output: Any = None,
    ) -> None:
        self.message = message
        self.updated_mcp_tool_output = updated_mcp_tool_output


# ---------------------------------------------------------------------------
# Permission decision resolution
# ---------------------------------------------------------------------------


async def resolve_hook_permission_decision(
    hook_permission_result: Optional[Any],
    tool: Any,
    input: Dict[str, Any],
    tool_use_context: Any,
    can_use_tool: Any,
    assistant_message: Any,
    tool_use_id: str,
) -> Dict[str, Any]:
    """Resolve a PreToolUse hook's permission result into a final PermissionDecision.

    Encapsulates the invariant that hook 'allow' does NOT bypass settings.json
    deny/ask rules. Also handles the requiresUserInteraction/requireCanUseTool
    guards and the 'ask' forceDecision passthrough.

    Returns:
        Dict with 'decision' and 'input' keys.
    """
    require_can_use_tool = getattr(tool_use_context, "require_can_use_tool", False)
    requires_interaction_fn = getattr(tool, "requires_user_interaction", None)
    requires_interaction = requires_interaction_fn() if callable(requires_interaction_fn) else False

    hook_behavior = getattr(hook_permission_result, "behavior", None) if hook_permission_result else None

    if hook_behavior == "allow":
        hook_input = getattr(hook_permission_result, "updated_input", None) or input

        # Check if hook satisfied the required user interaction
        interaction_satisfied = (
            requires_interaction
            and getattr(hook_permission_result, "updated_input", None) is not None
        )

        if (requires_interaction and not interaction_satisfied) or require_can_use_tool:
            log_for_debugging(
                f"Hook approved tool use for {getattr(tool, 'name', '?')}, "
                "but canUseTool is required"
            )
            decision = await _call_can_use_tool(
                can_use_tool, tool, hook_input, tool_use_context,
                assistant_message, tool_use_id
            )
            return {"decision": decision, "input": hook_input}

        # Hook allow skips the interactive prompt, but deny/ask rules still apply.
        rule_check = await _check_rule_based_permissions(tool, hook_input, tool_use_context)
        if rule_check is None:
            if interaction_satisfied:
                log_for_debugging(
                    f"Hook satisfied user interaction for {getattr(tool, 'name', '?')} "
                    "via updatedInput"
                )
            else:
                log_for_debugging(
                    f"Hook approved tool use for {getattr(tool, 'name', '?')}, "
                    "bypassing permission prompt"
                )
            return {"decision": hook_permission_result, "input": hook_input}

        rule_behavior = getattr(rule_check, "behavior", None)
        if rule_behavior == "deny":
            log_for_debugging(
                f"Hook approved tool use for {getattr(tool, 'name', '?')}, "
                f"but deny rule overrides: {getattr(rule_check, 'message', '')}"
            )
            return {"decision": rule_check, "input": hook_input}

        # ask rule — dialog required despite hook approval
        log_for_debugging(
            f"Hook approved tool use for {getattr(tool, 'name', '?')}, "
            "but ask rule requires prompt"
        )
        decision = await _call_can_use_tool(
            can_use_tool, tool, hook_input, tool_use_context,
            assistant_message, tool_use_id
        )
        return {"decision": decision, "input": hook_input}

    if hook_behavior == "deny":
        log_for_debugging(f"Hook denied tool use for {getattr(tool, 'name', '?')}")
        return {"decision": hook_permission_result, "input": input}

    # No hook decision or 'ask' — normal permission flow
    force_decision = hook_permission_result if hook_behavior == "ask" else None
    ask_input = (
        getattr(hook_permission_result, "updated_input", None) or input
        if hook_behavior == "ask"
        else input
    )

    decision = await _call_can_use_tool(
        can_use_tool, tool, ask_input, tool_use_context,
        assistant_message, tool_use_id, force_decision
    )
    return {"decision": decision, "input": ask_input}


async def _call_can_use_tool(
    can_use_tool: Any,
    tool: Any,
    input: Dict[str, Any],
    tool_use_context: Any,
    assistant_message: Any,
    tool_use_id: str,
    force_decision: Any = None,
) -> Any:
    """Call can_use_tool with proper arguments."""
    try:
        if force_decision is not None:
            result = can_use_tool(
                tool, input, tool_use_context, assistant_message,
                tool_use_id, force_decision
            )
        else:
            result = can_use_tool(
                tool, input, tool_use_context, assistant_message, tool_use_id
            )
        if asyncio.iscoroutine(result):
            return await result
        return result
    except Exception as e:
        log_error(e)
        # Return a deny decision on error
        class _DenyDecision:
            behavior = "deny"
            message = str(e)
        return _DenyDecision()


async def _check_rule_based_permissions(
    tool: Any,
    input: Dict[str, Any],
    tool_use_context: Any,
) -> Optional[Any]:
    """Check rule-based permissions. Returns None if no rule applies."""
    try:
        from ...utils.permissions.permissions import check_rule_based_permissions  # type: ignore
        result = check_rule_based_permissions(tool, input, tool_use_context)
        if asyncio.iscoroutine(result):
            return await result
        return result
    except (ImportError, Exception):
        return None


# ---------------------------------------------------------------------------
# PreToolUse hooks
# ---------------------------------------------------------------------------


async def run_pre_tool_use_hooks(
    tool_use_context: Any,
    tool: Any,
    processed_input: Dict[str, Any],
    tool_use_id: str,
    message_id: str,
    request_id: Optional[str],
    mcp_server_type: Optional[str],
    mcp_server_base_url: Optional[str],
) -> AsyncGenerator[Dict[str, Any], None]:
    """Run PreToolUse hooks and yield typed results.

    Yields dicts with type in:
      'message', 'hookPermissionResult', 'hookUpdatedInput',
      'preventContinuation', 'stopReason', 'additionalContext', 'stop'
    """
    hook_start_time = time.monotonic()

    try:
        from ...utils.hooks import execute_pre_tool_hooks  # type: ignore
        from ...utils.attachments import create_attachment_message  # type: ignore
    except ImportError:
        return

    try:
        app_state = tool_use_context.get_app_state()
        permission_mode = getattr(
            getattr(app_state, "tool_permission_context", None),
            "mode",
            "default",
        )

        async for result in _execute_pre_tool_hooks(
            getattr(tool, "name", "unknown"),
            tool_use_id,
            processed_input,
            tool_use_context,
            permission_mode,
            tool_use_context.abort_controller.signal,
            request_prompt=getattr(tool_use_context, "request_prompt", None),
            tool_use_summary=(
                tool.get_tool_use_summary(processed_input)
                if hasattr(tool, "get_tool_use_summary") else None
            ),
        ):
            try:
                # Forward progress messages
                msg = result.get("message")
                if msg:
                    yield {"type": "message", "message": {"message": msg}}

                # Blocking error → deny permission
                blocking_error = result.get("blocking_error") or result.get("blockingError")
                if blocking_error:
                    denial_msg = f"PreToolUse:{getattr(tool, 'name', '?')} blocked: {blocking_error}"
                    yield {
                        "type": "hookPermissionResult",
                        "hookPermissionResult": {
                            "behavior": "deny",
                            "message": denial_msg,
                            "decisionReason": {
                                "type": "hook",
                                "hookName": f"PreToolUse:{getattr(tool, 'name', '?')}",
                                "reason": denial_msg,
                            },
                        },
                    }

                # Prevent continuation flag
                if result.get("preventContinuation") or result.get("prevent_continuation"):
                    yield {"type": "preventContinuation", "shouldPreventContinuation": True}
                    stop_reason = result.get("stopReason") or result.get("stop_reason")
                    if stop_reason:
                        yield {"type": "stopReason", "stopReason": stop_reason}

                # Permission behavior from hook
                perm_behavior = (
                    result.get("permissionBehavior") or result.get("permission_behavior")
                )
                if perm_behavior is not None:
                    log_for_debugging(f"Hook result has permissionBehavior={perm_behavior}")
                    decision_reason = {
                        "type": "hook",
                        "hookName": f"PreToolUse:{getattr(tool, 'name', '?')}",
                        "hookSource": result.get("hookSource") or result.get("hook_source"),
                        "reason": (
                            result.get("hookPermissionDecisionReason")
                            or result.get("hook_permission_decision_reason")
                        ),
                    }
                    updated_input = result.get("updatedInput") or result.get("updated_input")
                    if perm_behavior == "allow":
                        yield {
                            "type": "hookPermissionResult",
                            "hookPermissionResult": {
                                "behavior": "allow",
                                "updated_input": updated_input,
                                "decisionReason": decision_reason,
                            },
                        }
                    elif perm_behavior == "ask":
                        ask_msg = (
                            result.get("hookPermissionDecisionReason")
                            or result.get("hook_permission_decision_reason")
                            or f"Hook PreToolUse:{getattr(tool, 'name', '?')} requested this tool"
                        )
                        yield {
                            "type": "hookPermissionResult",
                            "hookPermissionResult": {
                                "behavior": "ask",
                                "updated_input": updated_input,
                                "message": ask_msg,
                                "decisionReason": decision_reason,
                            },
                        }
                    else:
                        deny_msg = (
                            result.get("hookPermissionDecisionReason")
                            or result.get("hook_permission_decision_reason")
                            or f"Hook PreToolUse:{getattr(tool, 'name', '?')} blocked this tool"
                        )
                        yield {
                            "type": "hookPermissionResult",
                            "hookPermissionResult": {
                                "behavior": perm_behavior,
                                "message": deny_msg,
                                "decisionReason": decision_reason,
                            },
                        }

                # Updated input without permission decision (passthrough)
                updated_input = result.get("updatedInput") or result.get("updated_input")
                if updated_input and perm_behavior is None:
                    yield {"type": "hookUpdatedInput", "updatedInput": updated_input}

                # Additional contexts
                additional_contexts = (
                    result.get("additionalContexts") or result.get("additional_contexts")
                )
                if additional_contexts:
                    try:
                        att = create_attachment_message({
                            "type": "hook_additional_context",
                            "content": additional_contexts,
                            "hookName": f"PreToolUse:{getattr(tool, 'name', '?')}",
                            "toolUseID": tool_use_id,
                            "hookEvent": "PreToolUse",
                        })
                        yield {"type": "additionalContext", "message": {"message": att}}
                    except Exception:
                        pass

                # Check abort
                signal = getattr(tool_use_context, "abort_controller", None)
                aborted = (
                    getattr(signal, "aborted", False)
                    if signal
                    else False
                )
                if not aborted and hasattr(tool_use_context, "abort_controller"):
                    sig = tool_use_context.abort_controller
                    if hasattr(sig, "signal"):
                        sig = sig.signal
                    aborted = getattr(sig, "aborted", False)

                if aborted:
                    yield {"type": "stop"}
                    return

            except Exception as inner_e:
                log_error(inner_e)
                duration_ms = int((time.monotonic() - hook_start_time) * 1000)
                try:
                    from ...utils.tool_errors import format_error  # type: ignore
                    err_content = format_error(inner_e)
                except Exception:
                    err_content = str(inner_e)
                try:
                    att = create_attachment_message({
                        "type": "hook_error_during_execution",
                        "content": err_content,
                        "hookName": f"PreToolUse:{getattr(tool, 'name', '?')}",
                        "toolUseID": tool_use_id,
                        "hookEvent": "PreToolUse",
                    })
                    yield {"type": "message", "message": {"message": att}}
                except Exception:
                    pass
                yield {"type": "stop"}

    except Exception as outer_e:
        log_error(outer_e)
        yield {"type": "stop"}


async def _execute_pre_tool_hooks(
    tool_name: str,
    tool_use_id: str,
    processed_input: Dict[str, Any],
    tool_use_context: Any,
    permission_mode: str,
    signal: Any,
    request_prompt: Optional[str] = None,
    tool_use_summary: Optional[str] = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Delegate to the utils hooks layer."""
    try:
        from ...utils.hooks_execute import execute_pre_tool_hooks  # type: ignore
        async for result in execute_pre_tool_hooks(
            tool_name,
            tool_use_id,
            processed_input,
            tool_use_context,
            permission_mode,
            signal,
            timeout_ms=None,
            request_prompt=request_prompt,
            tool_use_summary=tool_use_summary,
        ):
            yield result
    except ImportError:
        try:
            from ...utils.hooks import execute_pre_tool_hooks as _ep  # type: ignore
            async for result in _ep(tool_name, tool_use_id, processed_input):
                yield result
        except (ImportError, Exception):
            return
    except Exception as e:
        log_error(e)


# ---------------------------------------------------------------------------
# PostToolUse hooks
# ---------------------------------------------------------------------------


async def run_post_tool_use_hooks(
    tool_use_context: Any,
    tool: Any,
    tool_use_id: str,
    message_id: str,
    tool_input: Dict[str, Any],
    tool_response: Any,
    request_id: Optional[str],
    mcp_server_type: Optional[str],
    mcp_server_base_url: Optional[str],
) -> AsyncGenerator[Any, None]:
    """Run PostToolUse hooks. Yields PostToolUseHooksResult or updatedMCPToolOutput dicts."""
    post_tool_start_time = time.monotonic()

    try:
        app_state = tool_use_context.get_app_state()
        permission_mode = getattr(
            getattr(app_state, "tool_permission_context", None),
            "mode",
            "default",
        )
    except Exception:
        permission_mode = "default"

    is_mcp = getattr(tool, "is_mcp", False) or getattr(tool, "isMcp", False)
    tool_output = tool_response

    try:
        async for result in _execute_post_tool_hooks(
            getattr(tool, "name", "unknown"),
            tool_use_id,
            tool_input,
            tool_output,
            tool_use_context,
            permission_mode,
            getattr(getattr(tool_use_context, "abort_controller", None), "signal", None),
        ):
            try:
                # Check for hook_cancelled
                msg = result.get("message")
                if (
                    msg
                    and getattr(msg, "type", None) == "attachment"
                    and getattr(getattr(msg, "attachment", None), "type", None) == "hook_cancelled"
                ):
                    try:
                        from ...utils.attachments import create_attachment_message  # type: ignore
                        att = create_attachment_message({
                            "type": "hook_cancelled",
                            "hookName": f"PostToolUse:{getattr(tool, 'name', '?')}",
                            "toolUseID": tool_use_id,
                            "hookEvent": "PostToolUse",
                        })
                        yield {"message": att}
                    except Exception:
                        pass
                    continue

                # Forward non-hook_blocking_error messages
                if msg:
                    att_type = None
                    if hasattr(msg, "type") and msg.type == "attachment":
                        att_type = getattr(getattr(msg, "attachment", None), "type", None)
                    if att_type != "hook_blocking_error":
                        yield {"message": msg}

                # Blocking error
                blocking_error = result.get("blocking_error") or result.get("blockingError")
                if blocking_error:
                    try:
                        from ...utils.attachments import create_attachment_message  # type: ignore
                        att = create_attachment_message({
                            "type": "hook_blocking_error",
                            "hookName": f"PostToolUse:{getattr(tool, 'name', '?')}",
                            "toolUseID": tool_use_id,
                            "hookEvent": "PostToolUse",
                            "blockingError": blocking_error,
                        })
                        yield {"message": att}
                    except Exception:
                        pass

                # Prevent continuation
                if result.get("preventContinuation") or result.get("prevent_continuation"):
                    stop_reason = result.get("stopReason") or result.get("stop_reason")
                    try:
                        from ...utils.attachments import create_attachment_message  # type: ignore
                        att = create_attachment_message({
                            "type": "hook_stopped_continuation",
                            "message": stop_reason or "Execution stopped by PostToolUse hook",
                            "hookName": f"PostToolUse:{getattr(tool, 'name', '?')}",
                            "toolUseID": tool_use_id,
                            "hookEvent": "PostToolUse",
                        })
                        yield {"message": att}
                    except Exception:
                        pass
                    return

                # Additional contexts
                additional_contexts = (
                    result.get("additionalContexts") or result.get("additional_contexts")
                )
                if additional_contexts:
                    try:
                        from ...utils.attachments import create_attachment_message  # type: ignore
                        att = create_attachment_message({
                            "type": "hook_additional_context",
                            "content": additional_contexts,
                            "hookName": f"PostToolUse:{getattr(tool, 'name', '?')}",
                            "toolUseID": tool_use_id,
                            "hookEvent": "PostToolUse",
                        })
                        yield {"message": att}
                    except Exception:
                        pass

                # Updated MCP tool output
                updated_output = (
                    result.get("updatedMCPToolOutput") or result.get("updated_mcp_tool_output")
                )
                if updated_output is not None and is_mcp:
                    tool_output = updated_output
                    yield {"updatedMCPToolOutput": tool_output}

            except Exception as inner_e:
                post_tool_duration_ms = int((time.monotonic() - post_tool_start_time) * 1000)
                log_error(inner_e)
                try:
                    from ...utils.tool_errors import format_error  # type: ignore
                    err_content = format_error(inner_e)
                except Exception:
                    err_content = str(inner_e)
                try:
                    from ...utils.attachments import create_attachment_message  # type: ignore
                    att = create_attachment_message({
                        "type": "hook_error_during_execution",
                        "content": err_content,
                        "hookName": f"PostToolUse:{getattr(tool, 'name', '?')}",
                        "toolUseID": tool_use_id,
                        "hookEvent": "PostToolUse",
                    })
                    yield {"message": att}
                except Exception:
                    pass

    except Exception as outer_e:
        log_error(outer_e)


async def _execute_post_tool_hooks(
    tool_name: str,
    tool_use_id: str,
    tool_input: Dict[str, Any],
    tool_output: Any,
    tool_use_context: Any,
    permission_mode: str,
    signal: Any,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Delegate to the utils hooks layer for PostToolUse."""
    try:
        from ...utils.hooks_execute import execute_post_tool_hooks  # type: ignore
        async for result in execute_post_tool_hooks(
            tool_name,
            tool_use_id,
            tool_input,
            tool_output,
            tool_use_context,
            permission_mode,
            signal,
        ):
            yield result
    except ImportError:
        try:
            from ...utils.hooks import execute_post_tool_hooks as _ep  # type: ignore
            async for result in _ep(tool_name, tool_use_id, tool_input, tool_output):
                yield result
        except (ImportError, Exception):
            return
    except Exception as e:
        log_error(e)


# ---------------------------------------------------------------------------
# PostToolUseFailure hooks
# ---------------------------------------------------------------------------


async def run_post_tool_use_failure_hooks(
    tool_use_context: Any,
    tool: Any,
    tool_use_id: str,
    message_id: str,
    processed_input: Any,
    error: str,
    is_interrupt: Optional[bool],
    request_id: Optional[str],
    mcp_server_type: Optional[str],
    mcp_server_base_url: Optional[str],
) -> AsyncGenerator[Any, None]:
    """Run PostToolUseFailure hooks."""
    post_tool_start_time = time.monotonic()

    try:
        app_state = tool_use_context.get_app_state()
        permission_mode = getattr(
            getattr(app_state, "tool_permission_context", None),
            "mode",
            "default",
        )
    except Exception:
        permission_mode = "default"

    try:
        async for result in _execute_post_tool_use_failure_hooks(
            getattr(tool, "name", "unknown"),
            tool_use_id,
            processed_input,
            error,
            tool_use_context,
            is_interrupt,
            permission_mode,
            getattr(getattr(tool_use_context, "abort_controller", None), "signal", None),
        ):
            try:
                msg = result.get("message")
                if (
                    msg
                    and hasattr(msg, "type")
                    and msg.type == "attachment"
                    and hasattr(msg, "attachment")
                    and getattr(msg.attachment, "type", None) == "hook_cancelled"
                ):
                    try:
                        from ...utils.attachments import create_attachment_message  # type: ignore
                        att = create_attachment_message({
                            "type": "hook_cancelled",
                            "hookName": f"PostToolUseFailure:{getattr(tool, 'name', '?')}",
                            "toolUseID": tool_use_id,
                            "hookEvent": "PostToolUseFailure",
                        })
                        yield {"message": att}
                    except Exception:
                        pass
                    continue

                # Forward non-hook_blocking_error messages
                if msg:
                    att_type = None
                    if hasattr(msg, "type") and msg.type == "attachment":
                        att_type = getattr(getattr(msg, "attachment", None), "type", None)
                    if att_type != "hook_blocking_error":
                        yield {"message": msg}

                # Blocking error
                blocking_error = result.get("blocking_error") or result.get("blockingError")
                if blocking_error:
                    try:
                        from ...utils.attachments import create_attachment_message  # type: ignore
                        att = create_attachment_message({
                            "type": "hook_blocking_error",
                            "hookName": f"PostToolUseFailure:{getattr(tool, 'name', '?')}",
                            "toolUseID": tool_use_id,
                            "hookEvent": "PostToolUseFailure",
                            "blockingError": blocking_error,
                        })
                        yield {"message": att}
                    except Exception:
                        pass

                # Additional contexts
                additional_contexts = (
                    result.get("additionalContexts") or result.get("additional_contexts")
                )
                if additional_contexts:
                    try:
                        from ...utils.attachments import create_attachment_message  # type: ignore
                        att = create_attachment_message({
                            "type": "hook_additional_context",
                            "content": additional_contexts,
                            "hookName": f"PostToolUseFailure:{getattr(tool, 'name', '?')}",
                            "toolUseID": tool_use_id,
                            "hookEvent": "PostToolUseFailure",
                        })
                        yield {"message": att}
                    except Exception:
                        pass

            except Exception as hook_error:
                log_error(hook_error)
                post_tool_duration_ms = int((time.monotonic() - post_tool_start_time) * 1000)
                try:
                    from ...utils.tool_errors import format_error  # type: ignore
                    err_content = format_error(hook_error)
                except Exception:
                    err_content = str(hook_error)
                try:
                    from ...utils.attachments import create_attachment_message  # type: ignore
                    att = create_attachment_message({
                        "type": "hook_error_during_execution",
                        "content": err_content,
                        "hookName": f"PostToolUseFailure:{getattr(tool, 'name', '?')}",
                        "toolUseID": tool_use_id,
                        "hookEvent": "PostToolUseFailure",
                    })
                    yield {"message": att}
                except Exception:
                    pass

    except Exception as outer_e:
        log_error(outer_e)


async def _execute_post_tool_use_failure_hooks(
    tool_name: str,
    tool_use_id: str,
    processed_input: Any,
    error: str,
    tool_use_context: Any,
    is_interrupt: Optional[bool],
    permission_mode: str,
    signal: Any,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Delegate to the utils hooks layer for PostToolUseFailure."""
    try:
        from ...utils.hooks_execute import execute_post_tool_use_failure_hooks  # type: ignore
        async for result in execute_post_tool_use_failure_hooks(
            tool_name,
            tool_use_id,
            processed_input,
            error,
            tool_use_context,
            is_interrupt,
            permission_mode,
            signal,
        ):
            yield result
    except ImportError:
        try:
            from ...utils.hooks import execute_post_tool_use_failure_hooks as _ep  # type: ignore
            async for result in _ep(tool_name, tool_use_id, processed_input, error):
                yield result
        except (ImportError, Exception):
            return
    except Exception as e:
        log_error(e)

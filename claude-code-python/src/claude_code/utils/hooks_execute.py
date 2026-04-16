"""
hooks_execute.py — Python port of utils/hooks.ts (lines 1601–5022).

Contains all execute* async functions for the Claude Code hook system.

Original TypeScript source: utils/hooks.ts
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncGenerator,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
    Union,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOOL_HOOK_EXECUTION_TIMEOUT_MS: int = 60_000  # 60 seconds


# ---------------------------------------------------------------------------
# Minimal stubs for types referenced from hooks_types / hooks_core
# (real implementations live in those modules; we import them if available)
# ---------------------------------------------------------------------------

try:
    from claude_code.utils.hooks.hook_events import (  # type: ignore[import]
        HookEvent,
    )
except ImportError:
    HookEvent = str  # type: ignore[assignment, misc]

# Lightweight dataclass stand-ins so the module is importable standalone.


@dataclass
class HookBlockingError:
    blocking_error: str
    command: str = ""


@dataclass
class HookOutsideReplResult:
    command: str
    succeeded: bool
    output: str
    blocked: bool
    watch_paths: List[str] = field(default_factory=list)
    system_message: Optional[str] = None


@dataclass
class ElicitationResponse:
    action: str  # 'accept' | 'decline' | 'cancel'
    content: Optional[Dict[str, Any]] = None


@dataclass
class ElicitationHookResult:
    elicitation_response: Optional[ElicitationResponse] = None
    blocking_error: Optional[HookBlockingError] = None


@dataclass
class ElicitationResultHookResult:
    elicitation_result_response: Optional[ElicitationResponse] = None
    blocking_error: Optional[HookBlockingError] = None


# AggregatedHookResult is a dict-like object yielded by executeHooks.
# In the Python port we use TypedDict-style dicts for simplicity.
AggregatedHookResult = Dict[str, Any]


# ---------------------------------------------------------------------------
# Stub helpers (replace with real implementations when available)
# ---------------------------------------------------------------------------

def _log_debug(msg: str, *, level: str = "debug") -> None:
    """Minimal debug logger stub."""
    if os.getenv("CLAUDE_CODE_DEBUG"):
        print(f"[hooks_execute:{level}] {msg}", file=sys.stderr)


def _should_disable_all_hooks() -> bool:
    return os.getenv("CLAUDE_CODE_DISABLE_HOOKS", "").lower() in ("1", "true", "yes")


def _is_env_truthy(val: Optional[str]) -> bool:
    return (val or "").lower() in ("1", "true", "yes")


def _should_skip_hook_due_to_trust() -> bool:
    return os.getenv("CLAUDE_CODE_SKIP_HOOKS_TRUST", "").lower() in ("1", "true", "yes")


def _should_allow_managed_hooks_only() -> bool:
    return os.getenv("CLAUDE_CODE_MANAGED_HOOKS_ONLY", "").lower() in ("1", "true", "yes")


def _get_session_id() -> str:
    return os.getenv("CLAUDE_SESSION_ID", "default")


def _get_settings_deprecated() -> Optional[Dict[str, Any]]:
    """Stub: return settings dict or None."""
    return None


def _get_settings_for_source(source: str) -> Optional[Dict[str, Any]]:
    """Stub: return settings for the given source."""
    return None


def _has_hook_for_event(
    event: str,
    app_state: Any = None,
    session_id: Optional[str] = None,
) -> bool:
    """Stub: check whether any hook is registered for *event*."""
    return False


def _get_hooks_config_from_snapshot() -> Optional[Dict[str, Any]]:
    return None


def _get_registered_hooks() -> Optional[Dict[str, Any]]:
    return None


def _clear_session_hooks(set_app_state: Any, session_id: str) -> None:
    pass


def _invalidate_session_env_cache() -> None:
    pass


def _create_base_hook_input(
    permission_mode: Optional[str] = None,
    session_id: Optional[str] = None,
    tool_use_context: Any = None,
) -> Dict[str, Any]:
    """Build the shared base fields for all hook inputs."""
    return {
        "session_id": session_id or _get_session_id(),
        "cwd": os.getcwd(),
        "permission_mode": permission_mode,
    }


async def _exec_command_hook(
    hook: Dict[str, Any],
    hook_event: str,
    hook_name: str,
    json_input: str,
    abort_signal: Any,  # asyncio.Event or similar
    hook_id: str,
    hook_index: int = 0,
    plugin_root: Optional[str] = None,
    plugin_id: Optional[str] = None,
    skill_root: Optional[str] = None,
    force_sync: bool = False,
    request_prompt: Any = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> Dict[str, Any]:
    """Execute a single command hook subprocess and return result dict."""
    command = hook.get("command", "")
    shell = hook.get("shell", "bash")
    timeout_secs = timeout_ms / 1000.0

    env = {**os.environ}
    if plugin_root:
        env["CLAUDE_PLUGIN_ROOT"] = plugin_root
    if skill_root:
        env["CLAUDE_SKILL_ROOT"] = skill_root

    try:
        proc = await asyncio.create_subprocess_exec(
            shell, "-c", command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(input=json_input.encode()),
                timeout=timeout_secs,
            )
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                pass
            return {
                "aborted": True,
                "status": -1,
                "stdout": "",
                "stderr": f"Hook timed out after {timeout_ms}ms",
                "output": "",
                "backgrounded": False,
            }

        stdout = stdout_bytes.decode(errors="replace")
        stderr = stderr_bytes.decode(errors="replace")
        status = proc.returncode if proc.returncode is not None else -1

        return {
            "aborted": False,
            "backgrounded": False,
            "status": status,
            "stdout": stdout,
            "stderr": stderr,
            "output": stdout + stderr,
        }

    except Exception as exc:
        return {
            "aborted": False,
            "backgrounded": False,
            "status": 1,
            "stdout": "",
            "stderr": str(exc),
            "output": str(exc),
        }


def _parse_hook_output(stdout: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[str]]:
    """
    Try to parse hook stdout as JSON.
    Returns (json_dict, plain_text, validation_error).
    """
    stripped = stdout.strip()
    if not stripped.startswith("{"):
        return None, stripped if stripped else None, None
    try:
        parsed = json.loads(stripped)
        return parsed, None, None
    except json.JSONDecodeError as exc:
        return None, stripped, f"JSON parse error: {exc}"


def _parse_http_hook_output(body: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Parse HTTP hook response body as JSON. Returns (json, validation_error)."""
    if not body.strip():
        return None, None
    try:
        return json.loads(body), None
    except json.JSONDecodeError as exc:
        return None, str(exc)


def _is_async_hook_json_output(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get("type") == "async"


def _is_sync_hook_json_output(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get("type") != "async"


def _process_hook_json_output(
    *,
    json_obj: Dict[str, Any],
    command: str,
    hook_name: str,
    tool_use_id: str,
    hook_event: str,
    stdout: Optional[str],
    stderr: Optional[str],
    exit_code: Optional[int],
    duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Convert a parsed hook JSON output to a partial HookResult dict.
    Mirrors processHookJSONOutput in the original TS.
    """
    result: Dict[str, Any] = {}

    decision = json_obj.get("decision")
    if decision == "block":
        result["blocking_error"] = HookBlockingError(
            blocking_error=json_obj.get("reason") or "Blocked by hook",
            command=command,
        )

    if json_obj.get("system_message"):
        result["system_message"] = json_obj["system_message"]

    if json_obj.get("additional_context"):
        result["additional_context"] = json_obj["additional_context"]

    if json_obj.get("initial_user_message"):
        result["initial_user_message"] = json_obj["initial_user_message"]

    if json_obj.get("stop_reason"):
        result["stop_reason"] = json_obj["stop_reason"]
        result["prevent_continuation"] = True

    # permission_behavior
    pb = json_obj.get("permission_behavior") or json_obj.get("permissionDecision")
    if pb:
        result["permission_behavior"] = pb

    if json_obj.get("updated_input"):
        result["updated_input"] = json_obj["updated_input"]

    if json_obj.get("updated_mcp_tool_output"):
        result["updated_mcp_tool_output"] = json_obj["updated_mcp_tool_output"]

    if json_obj.get("watch_paths"):
        result["watch_paths"] = json_obj["watch_paths"]

    if json_obj.get("elicitation_response"):
        result["elicitation_response"] = json_obj["elicitation_response"]

    if json_obj.get("elicitation_result_response"):
        result["elicitation_result_response"] = json_obj["elicitation_result_response"]

    if json_obj.get("permission_request_result"):
        result["permission_request_result"] = json_obj["permission_request_result"]

    if json_obj.get("retry"):
        result["retry"] = json_obj["retry"]

    # hook_specific_output (WorktreeCreate, etc.)
    hso = json_obj.get("hookSpecificOutput") or json_obj.get("hook_specific_output")
    if hso:
        result["hook_specific_output"] = hso

    return result


def _create_attachment_message(
    *,
    msg_type: str,
    hook_name: str,
    tool_use_id: str,
    hook_event: str,
    content: Optional[str] = None,
    stdout: Optional[str] = None,
    stderr: Optional[str] = None,
    exit_code: Optional[int] = None,
    command: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> Dict[str, Any]:
    return {
        "type": "attachment",
        "attachment": {
            "type": msg_type,
            "hook_name": hook_name,
            "hook_event": hook_event,
            "content": content,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": exit_code,
            "command": command,
            "duration_ms": duration_ms,
        },
        "parent_tool_use_id": tool_use_id,
        "tool_use_id": tool_use_id,
    }


# ---------------------------------------------------------------------------
# Stub: get_matching_hooks
# ---------------------------------------------------------------------------

async def _get_matching_hooks(
    app_state: Any,
    session_id: str,
    hook_event: str,
    hook_input: Dict[str, Any],
    tools: Any = None,
) -> List[Dict[str, Any]]:
    """
    Stub implementation. Returns an empty list; replace with real logic
    by importing from hooks_config_manager when available.
    """
    try:
        from claude_code.utils.hooks.hooks_config_manager import get_matching_hooks  # type: ignore[import]
        return await get_matching_hooks(app_state, session_id, hook_event, hook_input, tools)
    except ImportError:
        return []


# ---------------------------------------------------------------------------
# Core executeHooks generator
# ---------------------------------------------------------------------------

async def _execute_hooks(
    *,
    hook_input: Dict[str, Any],
    tool_use_id: str,
    match_query: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    tool_use_context: Any = None,
    messages: Optional[List[Any]] = None,
    force_sync_execution: bool = False,
    request_prompt: Any = None,
    tool_input_summary: Optional[str] = None,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """
    Core hook executor (mirrors executeHooks in hooks.ts).
    Yields AggregatedHookResult dicts.
    """
    if _should_disable_all_hooks():
        return

    if _is_env_truthy(os.getenv("CLAUDE_CODE_SIMPLE")):
        return

    if _should_skip_hook_due_to_trust():
        _log_debug(f"Skipping hooks due to trust check")
        return

    hook_event = hook_input.get("hook_event_name", "")
    hook_name = f"{hook_event}:{match_query}" if match_query else hook_event

    app_state = tool_use_context.get_app_state() if tool_use_context else None
    session_id = (
        getattr(tool_use_context, "agent_id", None) or _get_session_id()
    )

    matching_hooks = await _get_matching_hooks(
        app_state,
        session_id,
        hook_event,
        hook_input,
    )

    if not matching_hooks:
        return

    if signal and signal.is_set():
        return

    # Yield a progress message for each hook
    for matched in matching_hooks:
        hook = matched.get("hook", {})
        yield {
            "message": _create_attachment_message(
                msg_type="hook_progress",
                hook_name=hook_name,
                tool_use_id=tool_use_id,
                hook_event=hook_event,
                command=hook.get("command") or hook.get("url") or hook.get("prompt", ""),
            )
        }

    batch_start = asyncio.get_event_loop().time()

    # Stringify hook input once
    try:
        json_input = json.dumps(hook_input, default=str)
    except Exception as exc:
        _log_debug(f"Failed to stringify hook input: {exc}", level="error")
        return

    # Run all hooks concurrently
    tasks = []
    for idx, matched in enumerate(matching_hooks):
        hook = matched.get("hook", {})
        plugin_root = matched.get("plugin_root")
        plugin_id = matched.get("plugin_id")
        skill_root = matched.get("skill_root")
        tasks.append(
            _run_single_hook(
                hook=hook,
                hook_name=hook_name,
                hook_event=hook_event,
                json_input=json_input,
                hook_input=hook_input,
                tool_use_id=tool_use_id,
                timeout_ms=timeout_ms,
                signal=signal,
                plugin_root=plugin_root,
                plugin_id=plugin_id,
                skill_root=skill_root,
                hook_index=idx,
                force_sync=force_sync_execution,
                tool_use_context=tool_use_context,
                messages=messages,
            )
        )

    results = await asyncio.gather(*tasks, return_exceptions=True)

    for res in results:
        if isinstance(res, Exception):
            _log_debug(f"Hook task raised exception: {res}", level="error")
            continue
        if not isinstance(res, dict):
            continue

        # Yield sub-results
        if res.get("blocking_error"):
            yield {"blocking_error": res["blocking_error"]}
        if res.get("message"):
            yield {"message": res["message"]}
        if res.get("system_message"):
            yield {
                "message": _create_attachment_message(
                    msg_type="hook_system_message",
                    hook_name=hook_name,
                    tool_use_id=tool_use_id,
                    hook_event=hook_event,
                    content=res["system_message"],
                )
            }
        if res.get("additional_context"):
            yield {"additional_contexts": [res["additional_context"]]}
        if res.get("initial_user_message"):
            yield {"initial_user_message": res["initial_user_message"]}
        if res.get("watch_paths"):
            yield {"watch_paths": res["watch_paths"]}
        if res.get("updated_mcp_tool_output"):
            yield {"updated_mcp_tool_output": res["updated_mcp_tool_output"]}
        if res.get("prevent_continuation"):
            yield {"prevent_continuation": True, "stop_reason": res.get("stop_reason")}
        if res.get("permission_behavior"):
            yield {
                "permission_behavior": res["permission_behavior"],
                "hook_permission_decision_reason": res.get("hook_permission_decision_reason"),
                "updated_input": res.get("updated_input"),
            }
        elif res.get("updated_input"):
            yield {"updated_input": res["updated_input"]}
        if res.get("permission_request_result"):
            yield {"permission_request_result": res["permission_request_result"]}
        if res.get("retry"):
            yield {"retry": res["retry"]}
        if res.get("elicitation_response"):
            yield {"elicitation_response": res["elicitation_response"]}
        if res.get("elicitation_result_response"):
            yield {"elicitation_result_response": res["elicitation_result_response"]}


async def _run_single_hook(
    *,
    hook: Dict[str, Any],
    hook_name: str,
    hook_event: str,
    json_input: str,
    hook_input: Dict[str, Any],
    tool_use_id: str,
    timeout_ms: int,
    signal: Optional[asyncio.Event],
    plugin_root: Optional[str],
    plugin_id: Optional[str],
    skill_root: Optional[str],
    hook_index: int,
    force_sync: bool,
    tool_use_context: Any,
    messages: Optional[List[Any]],
) -> Dict[str, Any]:
    """Execute a single matched hook and return a result dict."""
    hook_type = hook.get("type", "command")
    hook_start_ms = int(asyncio.get_event_loop().time() * 1000)
    hook_command = hook.get("command") or hook.get("url") or hook.get("prompt", "unknown")
    command_timeout_ms = hook.get("timeout", 0) * 1000 if hook.get("timeout") else timeout_ms

    # ---- callback hook ----
    if hook_type == "callback":
        callback = hook.get("callback")
        if callback is None:
            return {"outcome": "non_blocking_error"}
        try:
            json_out = await asyncio.wait_for(
                asyncio.coroutine(callback)(hook_input, tool_use_id, signal, hook_index)
                if asyncio.iscoroutinefunction(callback)
                else asyncio.get_event_loop().run_in_executor(None, callback, hook_input, tool_use_id),
                timeout=command_timeout_ms / 1000.0,
            )
            if _is_async_hook_json_output(json_out):
                return {"outcome": "success", "hook": hook}
            processed = _process_hook_json_output(
                json_obj=json_out or {},
                command="callback",
                hook_name=hook_name,
                tool_use_id=tool_use_id,
                hook_event=hook_event,
                stdout=None,
                stderr=None,
                exit_code=None,
            )
            return {**processed, "outcome": "success", "hook": hook}
        except Exception as exc:
            return {
                "message": _create_attachment_message(
                    msg_type="hook_error_during_execution",
                    hook_name=hook_name,
                    tool_use_id=tool_use_id,
                    hook_event=hook_event,
                    content=str(exc),
                ),
                "outcome": "non_blocking_error",
                "hook": hook,
            }

    # ---- command hook ----
    if hook_type == "command":
        result = await _exec_command_hook(
            hook=hook,
            hook_event=hook_event,
            hook_name=hook_name,
            json_input=json_input,
            abort_signal=signal,
            hook_id=str(uuid.uuid4()),
            hook_index=hook_index,
            plugin_root=plugin_root,
            plugin_id=plugin_id,
            skill_root=skill_root,
            force_sync=force_sync,
            timeout_ms=command_timeout_ms,
        )
        duration_ms = int(asyncio.get_event_loop().time() * 1000) - hook_start_ms

        if result.get("aborted"):
            return {
                "message": _create_attachment_message(
                    msg_type="hook_cancelled",
                    hook_name=hook_name,
                    tool_use_id=tool_use_id,
                    hook_event=hook_event,
                    command=hook_command,
                    duration_ms=duration_ms,
                ),
                "outcome": "cancelled",
                "hook": hook,
            }

        json_obj, plain_text, validation_error = _parse_hook_output(result.get("stdout", ""))

        if validation_error:
            return {
                "message": _create_attachment_message(
                    msg_type="hook_non_blocking_error",
                    hook_name=hook_name,
                    tool_use_id=tool_use_id,
                    hook_event=hook_event,
                    stderr=f"JSON validation failed: {validation_error}",
                    stdout=result.get("stdout", ""),
                    exit_code=1,
                    command=hook_command,
                    duration_ms=duration_ms,
                ),
                "outcome": "non_blocking_error",
                "hook": hook,
            }

        if json_obj:
            if _is_async_hook_json_output(json_obj):
                return {"outcome": "success", "hook": hook}
            processed = _process_hook_json_output(
                json_obj=json_obj,
                command=hook_command,
                hook_name=hook_name,
                tool_use_id=tool_use_id,
                hook_event=hook_event,
                stdout=result.get("stdout"),
                stderr=result.get("stderr"),
                exit_code=result.get("status"),
                duration_ms=duration_ms,
            )
            return {**processed, "outcome": "success", "hook": hook}

        status = result.get("status", -1)
        if status == 0:
            return {
                "message": _create_attachment_message(
                    msg_type="hook_success",
                    hook_name=hook_name,
                    tool_use_id=tool_use_id,
                    hook_event=hook_event,
                    content=(result.get("stdout") or "").strip(),
                    stdout=result.get("stdout"),
                    stderr=result.get("stderr"),
                    exit_code=status,
                    command=hook_command,
                    duration_ms=duration_ms,
                ),
                "outcome": "success",
                "hook": hook,
            }

        if status == 2:
            return {
                "blocking_error": HookBlockingError(
                    blocking_error=f"[{hook.get('command', '')}]: {result.get('stderr') or 'No stderr output'}",
                    command=hook.get("command", ""),
                ),
                "outcome": "blocking",
                "hook": hook,
            }

        return {
            "message": _create_attachment_message(
                msg_type="hook_non_blocking_error",
                hook_name=hook_name,
                tool_use_id=tool_use_id,
                hook_event=hook_event,
                stderr=f"Failed with non-blocking status code: {(result.get('stderr') or '').strip() or 'No stderr output'}",
                stdout=result.get("stdout"),
                exit_code=status,
                command=hook_command,
                duration_ms=duration_ms,
            ),
            "outcome": "non_blocking_error",
            "hook": hook,
        }

    # ---- http hook ----
    if hook_type == "http":
        try:
            import aiohttp  # type: ignore[import]
            url = hook.get("url", "")
            http_timeout = hook.get("timeout", command_timeout_ms / 1000.0)
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    data=json_input,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=http_timeout),
                ) as resp:
                    body = await resp.text()
                    ok = resp.status < 400
                    status_code = resp.status

            if not ok:
                return {
                    "message": _create_attachment_message(
                        msg_type="hook_non_blocking_error",
                        hook_name=hook_name,
                        tool_use_id=tool_use_id,
                        hook_event=hook_event,
                        stderr=f"HTTP {status_code} from {url}",
                        stdout="",
                        exit_code=status_code,
                    ),
                    "outcome": "non_blocking_error",
                    "hook": hook,
                }

            http_json, http_val_error = _parse_http_hook_output(body)
            if http_val_error:
                return {
                    "message": _create_attachment_message(
                        msg_type="hook_non_blocking_error",
                        hook_name=hook_name,
                        tool_use_id=tool_use_id,
                        hook_event=hook_event,
                        stderr=f"JSON validation failed: {http_val_error}",
                        stdout=body,
                        exit_code=status_code,
                    ),
                    "outcome": "non_blocking_error",
                    "hook": hook,
                }

            if http_json and _is_async_hook_json_output(http_json):
                return {"outcome": "success", "hook": hook}

            if http_json:
                processed = _process_hook_json_output(
                    json_obj=http_json,
                    command=url,
                    hook_name=hook_name,
                    tool_use_id=tool_use_id,
                    hook_event=hook_event,
                    stdout=body,
                    stderr="",
                    exit_code=status_code,
                )
                return {**processed, "outcome": "success", "hook": hook}

            return {"outcome": "success", "hook": hook}

        except Exception as exc:
            return {
                "message": _create_attachment_message(
                    msg_type="hook_non_blocking_error",
                    hook_name=hook_name,
                    tool_use_id=tool_use_id,
                    hook_event=hook_event,
                    stderr=f"HTTP hook error: {exc}",
                    stdout="",
                    exit_code=1,
                ),
                "outcome": "non_blocking_error",
                "hook": hook,
            }

    # ---- prompt / agent hooks (stub) ----
    if hook_type in ("prompt", "agent"):
        _log_debug(f"Prompt/agent hooks not fully implemented for {hook_type}")
        return {"outcome": "non_blocking_error", "hook": hook}

    # ---- function hook ----
    if hook_type == "function":
        if not messages:
            return {
                "message": _create_attachment_message(
                    msg_type="hook_error_during_execution",
                    hook_name=hook_name,
                    tool_use_id=tool_use_id,
                    hook_event=hook_event,
                    content="Messages not provided for function hook",
                ),
                "outcome": "non_blocking_error",
                "hook": hook,
            }
        return await _execute_function_hook(
            hook=hook,
            messages=messages,
            hook_name=hook_name,
            tool_use_id=tool_use_id,
            hook_event=hook_event,
            timeout_ms=command_timeout_ms,
            signal=signal,
        )

    _log_debug(f"Unknown hook type: {hook_type}", level="warn")
    return {"outcome": "non_blocking_error", "hook": hook}


# ---------------------------------------------------------------------------
# executeHooksOutsideREPL
# ---------------------------------------------------------------------------

async def _execute_hooks_outside_repl(
    *,
    get_app_state: Any = None,
    hook_input: Dict[str, Any],
    match_query: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> List[HookOutsideReplResult]:
    """
    Execute hooks outside the REPL loop (notifications, session end, etc.).
    Returns a list of HookOutsideReplResult.
    """
    if _is_env_truthy(os.getenv("CLAUDE_CODE_SIMPLE")):
        return []

    if _should_disable_all_hooks():
        return []

    if _should_skip_hook_due_to_trust():
        return []

    hook_event = hook_input.get("hook_event_name", "")
    hook_name = f"{hook_event}:{match_query}" if match_query else hook_event

    app_state = get_app_state() if callable(get_app_state) else None
    session_id = _get_session_id()

    matching_hooks = await _get_matching_hooks(app_state, session_id, hook_event, hook_input)
    if not matching_hooks:
        return []

    if signal and signal.is_set():
        return []

    try:
        json_input = json.dumps(hook_input, default=str)
    except Exception as exc:
        _log_debug(f"Failed to stringify hook input for {hook_name}: {exc}", level="error")
        return []

    async def _run_one(matched: Dict[str, Any], idx: int) -> HookOutsideReplResult:
        hook = matched.get("hook", {})
        plugin_root = matched.get("plugin_root")
        plugin_id = matched.get("plugin_id")
        hook_type = hook.get("type", "command")
        cmd_timeout = hook.get("timeout", 0) * 1000 if hook.get("timeout") else timeout_ms

        # callback
        if hook_type == "callback":
            callback = hook.get("callback")
            if callback is None:
                return HookOutsideReplResult(command="callback", succeeded=False, output="No callback", blocked=False)
            try:
                json_out = await asyncio.wait_for(
                    asyncio.ensure_future(callback(hook_input, str(uuid.uuid4()), signal, idx))
                    if asyncio.iscoroutinefunction(callback)
                    else asyncio.get_event_loop().run_in_executor(None, callback, hook_input, str(uuid.uuid4())),
                    timeout=cmd_timeout / 1000.0,
                )
                if _is_async_hook_json_output(json_out):
                    return HookOutsideReplResult(command="callback", succeeded=True, output="", blocked=False)

                output = ""
                if hook_event == "WorktreeCreate":
                    hso = json_out.get("hookSpecificOutput") or json_out.get("hook_specific_output")
                    if hso and hso.get("hookEventName") == "WorktreeCreate":
                        output = hso.get("worktreePath", "")
                else:
                    output = json_out.get("systemMessage") or json_out.get("system_message", "")

                blocked = bool(json_out.get("decision") == "block")
                return HookOutsideReplResult(command="callback", succeeded=True, output=output, blocked=blocked)
            except Exception as exc:
                return HookOutsideReplResult(command="callback", succeeded=False, output=str(exc), blocked=False)

        # prompt/agent stubs
        if hook_type == "prompt":
            return HookOutsideReplResult(
                command=hook.get("prompt", ""),
                succeeded=False,
                output="Prompt stop hooks not yet supported outside REPL",
                blocked=False,
            )
        if hook_type == "agent":
            return HookOutsideReplResult(
                command=hook.get("prompt", ""),
                succeeded=False,
                output="Agent stop hooks not yet supported outside REPL",
                blocked=False,
            )
        if hook_type == "function":
            return HookOutsideReplResult(
                command="function",
                succeeded=False,
                output="Internal error: function hook executed outside REPL context",
                blocked=False,
            )

        # http
        if hook_type == "http":
            url = hook.get("url", "")
            try:
                import aiohttp  # type: ignore[import]
                http_timeout = hook.get("timeout", cmd_timeout / 1000.0)
                async with aiohttp.ClientSession() as sess:
                    async with sess.post(
                        url,
                        data=json_input,
                        headers={"Content-Type": "application/json"},
                        timeout=aiohttp.ClientTimeout(total=http_timeout),
                    ) as resp:
                        body = await resp.text()
                        ok = resp.status < 400
                        status_code = resp.status

                if not ok:
                    return HookOutsideReplResult(command=url, succeeded=False, output=f"HTTP {status_code}", blocked=False)

                http_json, http_val_err = _parse_http_hook_output(body)
                if http_val_err:
                    raise ValueError(http_val_err)

                if http_json and not _is_async_hook_json_output(http_json):
                    blocked_flag = bool(_is_sync_hook_json_output(http_json) and http_json.get("decision") == "block")
                    if hook_event == "WorktreeCreate":
                        hso = http_json.get("hookSpecificOutput") or http_json.get("hook_specific_output")
                        output = hso.get("worktreePath", "") if hso and hso.get("hookEventName") == "WorktreeCreate" else ""
                    else:
                        output = body
                    return HookOutsideReplResult(command=url, succeeded=True, output=output, blocked=blocked_flag)

                return HookOutsideReplResult(command=url, succeeded=True, output=body, blocked=False)
            except Exception as exc:
                return HookOutsideReplResult(command=url, succeeded=False, output=str(exc), blocked=False)

        # command (default)
        command_str = hook.get("command", "")
        result = await _exec_command_hook(
            hook=hook,
            hook_event=hook_event,
            hook_name=hook_name,
            json_input=json_input,
            abort_signal=signal,
            hook_id=str(uuid.uuid4()),
            hook_index=idx,
            plugin_root=plugin_root,
            plugin_id=plugin_id,
            timeout_ms=cmd_timeout,
        )

        if result.get("aborted"):
            return HookOutsideReplResult(command=command_str, succeeded=False, output="Hook cancelled", blocked=False)

        json_obj, _, val_error = _parse_hook_output(result.get("stdout", ""))
        if val_error:
            raise ValueError(val_error)

        if json_obj and not _is_async_hook_json_output(json_obj):
            json_blocked = bool(_is_sync_hook_json_output(json_obj) and json_obj.get("decision") == "block")
        else:
            json_blocked = False

        status = result.get("status", -1)
        blocked = status == 2 or json_blocked
        output = result.get("stdout", "") if status == 0 else result.get("stderr", "")

        watch_paths: List[str] = []
        system_message: Optional[str] = None
        if json_obj and _is_sync_hook_json_output(json_obj):
            hso = json_obj.get("hookSpecificOutput") or json_obj.get("hook_specific_output")
            if hso and "watchPaths" in hso:
                watch_paths = hso["watchPaths"]
            system_message = json_obj.get("systemMessage") or json_obj.get("system_message")

        return HookOutsideReplResult(
            command=command_str,
            succeeded=(status == 0),
            output=output,
            blocked=blocked,
            watch_paths=watch_paths,
            system_message=system_message,
        )

    tasks = [_run_one(m, i) for i, m in enumerate(matching_hooks)]
    results_raw = await asyncio.gather(*tasks, return_exceptions=True)
    out: List[HookOutsideReplResult] = []
    for r in results_raw:
        if isinstance(r, Exception):
            _log_debug(f"Outside-REPL hook raised: {r}", level="error")
        elif isinstance(r, HookOutsideReplResult):
            out.append(r)
    return out


# ---------------------------------------------------------------------------
# _execute_function_hook (helper used by _run_single_hook)
# ---------------------------------------------------------------------------

async def _execute_function_hook(
    *,
    hook: Dict[str, Any],
    messages: List[Any],
    hook_name: str,
    tool_use_id: str,
    hook_event: str,
    timeout_ms: int,
    signal: Optional[asyncio.Event],
) -> Dict[str, Any]:
    callback = hook.get("callback")
    error_message = hook.get("error_message") or hook.get("errorMessage", "Function hook returned false")
    cb_timeout = (hook.get("timeout") or timeout_ms / 1000.0)

    try:
        if asyncio.iscoroutinefunction(callback):
            passed = await asyncio.wait_for(callback(messages, signal), timeout=cb_timeout)
        else:
            passed = await asyncio.wait_for(
                asyncio.get_event_loop().run_in_executor(None, callback, messages),
                timeout=cb_timeout,
            )

        if passed:
            return {"outcome": "success", "hook": hook}
        return {
            "blocking_error": HookBlockingError(blocking_error=error_message, command="function"),
            "outcome": "blocking",
            "hook": hook,
        }
    except asyncio.TimeoutError:
        return {"outcome": "cancelled", "hook": hook}
    except Exception as exc:
        return {
            "message": _create_attachment_message(
                msg_type="hook_error_during_execution",
                hook_name=hook_name,
                tool_use_id=tool_use_id,
                hook_event=hook_event,
                content=str(exc),
            ),
            "outcome": "non_blocking_error",
            "hook": hook,
        }


# ---------------------------------------------------------------------------
# Utility: hasBlockingResult
# ---------------------------------------------------------------------------

def has_blocking_result(results: List[HookOutsideReplResult]) -> bool:
    """Return True if any result is blocked."""
    return any(r.blocked for r in results)


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def get_pre_tool_hook_blocking_message(hook_name: str, blocking_error: HookBlockingError) -> str:
    return f"{hook_name} hook error: {blocking_error.blocking_error}"


def get_stop_hook_message(blocking_error: HookBlockingError) -> str:
    return f"Stop hook feedback:\n{blocking_error.blocking_error}"


def get_teammate_idle_hook_message(blocking_error: HookBlockingError) -> str:
    return f"TeammateIdle hook feedback:\n{blocking_error.blocking_error}"


def get_task_created_hook_message(blocking_error: HookBlockingError) -> str:
    return f"TaskCreated hook feedback:\n{blocking_error.blocking_error}"


def get_task_completed_hook_message(blocking_error: HookBlockingError) -> str:
    return f"TaskCompleted hook feedback:\n{blocking_error.blocking_error}"


def get_user_prompt_submit_hook_blocking_message(blocking_error: HookBlockingError) -> str:
    return f"UserPromptSubmit operation blocked by hook:\n{blocking_error.blocking_error}"


# ---------------------------------------------------------------------------
# Public execute* functions
# ---------------------------------------------------------------------------


async def execute_pre_tool_hooks(
    tool_name: str,
    tool_use_id: str,
    tool_input: Any,
    tool_use_context: Any,
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    request_prompt: Any = None,
    tool_input_summary: Optional[str] = None,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute PreToolUse hooks."""
    app_state = tool_use_context.get_app_state() if tool_use_context else None
    session_id = getattr(tool_use_context, "agent_id", None) or _get_session_id()
    if not _has_hook_for_event("PreToolUse", app_state, session_id):
        return

    hook_input = {
        **_create_base_hook_input(permission_mode, None, tool_use_context),
        "hook_event_name": "PreToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": tool_use_id,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=tool_use_id,
        match_query=tool_name,
        signal=signal,
        timeout_ms=timeout_ms,
        tool_use_context=tool_use_context,
        request_prompt=request_prompt,
        tool_input_summary=tool_input_summary,
    ):
        yield result


async def execute_post_tool_hooks(
    tool_name: str,
    tool_use_id: str,
    tool_input: Any,
    tool_response: Any,
    tool_use_context: Any,
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute PostToolUse hooks."""
    hook_input = {
        **_create_base_hook_input(permission_mode, None, tool_use_context),
        "hook_event_name": "PostToolUse",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_response": tool_response,
        "tool_use_id": tool_use_id,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=tool_use_id,
        match_query=tool_name,
        signal=signal,
        timeout_ms=timeout_ms,
        tool_use_context=tool_use_context,
    ):
        yield result


async def execute_post_tool_use_failure_hooks(
    tool_name: str,
    tool_use_id: str,
    tool_input: Any,
    error: str,
    tool_use_context: Any,
    is_interrupt: Optional[bool] = None,
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute PostToolUseFailure hooks."""
    app_state = tool_use_context.get_app_state() if tool_use_context else None
    session_id = getattr(tool_use_context, "agent_id", None) or _get_session_id()
    if not _has_hook_for_event("PostToolUseFailure", app_state, session_id):
        return

    hook_input = {
        **_create_base_hook_input(permission_mode, None, tool_use_context),
        "hook_event_name": "PostToolUseFailure",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": tool_use_id,
        "error": error,
        "is_interrupt": is_interrupt,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=tool_use_id,
        match_query=tool_name,
        signal=signal,
        timeout_ms=timeout_ms,
        tool_use_context=tool_use_context,
    ):
        yield result


async def execute_permission_denied_hooks(
    tool_name: str,
    tool_use_id: str,
    tool_input: Any,
    reason: str,
    tool_use_context: Any,
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute PermissionDenied hooks."""
    app_state = tool_use_context.get_app_state() if tool_use_context else None
    session_id = getattr(tool_use_context, "agent_id", None) or _get_session_id()
    if not _has_hook_for_event("PermissionDenied", app_state, session_id):
        return

    hook_input = {
        **_create_base_hook_input(permission_mode, None, tool_use_context),
        "hook_event_name": "PermissionDenied",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "tool_use_id": tool_use_id,
        "reason": reason,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=tool_use_id,
        match_query=tool_name,
        signal=signal,
        timeout_ms=timeout_ms,
        tool_use_context=tool_use_context,
    ):
        yield result


async def execute_notification_hooks(
    notification_data: Dict[str, Any],
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> None:
    """Execute Notification hooks (fire-and-forget outside REPL)."""
    message = notification_data.get("message", "")
    title = notification_data.get("title")
    notification_type = notification_data.get("notificationType", "")

    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "Notification",
        "message": message,
        "title": title,
        "notification_type": notification_type,
    }

    await _execute_hooks_outside_repl(
        hook_input=hook_input,
        timeout_ms=timeout_ms,
        match_query=notification_type,
    )


async def execute_stop_failure_hooks(
    last_message: Any,
    tool_use_context: Any = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> None:
    """Execute StopFailure hooks."""
    app_state = tool_use_context.get_app_state() if tool_use_context else None
    session_id = _get_session_id()
    if not _has_hook_for_event("StopFailure", app_state, session_id):
        return

    error = getattr(last_message, "error", None) or "unknown"
    hook_input = {
        **_create_base_hook_input(None, None, tool_use_context),
        "hook_event_name": "StopFailure",
        "error": error,
    }

    await _execute_hooks_outside_repl(
        get_app_state=tool_use_context.get_app_state if tool_use_context else None,
        hook_input=hook_input,
        timeout_ms=timeout_ms,
        match_query=error,
    )


async def execute_stop_hooks(
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    stop_hook_active: bool = False,
    subagent_id: Optional[str] = None,
    tool_use_context: Any = None,
    messages: Optional[List[Any]] = None,
    agent_type: Optional[str] = None,
    request_prompt: Any = None,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute Stop or SubagentStop hooks."""
    hook_event = "SubagentStop" if subagent_id else "Stop"
    app_state = tool_use_context.get_app_state() if tool_use_context else None
    session_id = getattr(tool_use_context, "agent_id", None) or _get_session_id()
    if not _has_hook_for_event(hook_event, app_state, session_id):
        return

    if subagent_id:
        hook_input: Dict[str, Any] = {
            **_create_base_hook_input(permission_mode),
            "hook_event_name": "SubagentStop",
            "stop_hook_active": stop_hook_active,
            "agent_id": subagent_id,
            "agent_type": agent_type or "",
        }
    else:
        hook_input = {
            **_create_base_hook_input(permission_mode),
            "hook_event_name": "Stop",
            "stop_hook_active": stop_hook_active,
        }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=str(uuid.uuid4()),
        signal=signal,
        timeout_ms=timeout_ms,
        tool_use_context=tool_use_context,
        messages=messages,
        request_prompt=request_prompt,
    ):
        yield result


async def execute_teammate_idle_hooks(
    teammate_name: str,
    team_name: str,
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute TeammateIdle hooks."""
    hook_input = {
        **_create_base_hook_input(permission_mode),
        "hook_event_name": "TeammateIdle",
        "teammate_name": teammate_name,
        "team_name": team_name,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=str(uuid.uuid4()),
        signal=signal,
        timeout_ms=timeout_ms,
    ):
        yield result


async def execute_task_created_hooks(
    task_id: str,
    task_subject: str,
    task_description: Optional[str] = None,
    teammate_name: Optional[str] = None,
    team_name: Optional[str] = None,
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    tool_use_context: Any = None,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute TaskCreated hooks."""
    hook_input = {
        **_create_base_hook_input(permission_mode),
        "hook_event_name": "TaskCreated",
        "task_id": task_id,
        "task_subject": task_subject,
        "task_description": task_description,
        "teammate_name": teammate_name,
        "team_name": team_name,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=str(uuid.uuid4()),
        signal=signal,
        timeout_ms=timeout_ms,
        tool_use_context=tool_use_context,
    ):
        yield result


async def execute_task_completed_hooks(
    task_id: str,
    task_subject: str,
    task_description: Optional[str] = None,
    teammate_name: Optional[str] = None,
    team_name: Optional[str] = None,
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    tool_use_context: Any = None,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute TaskCompleted hooks."""
    hook_input = {
        **_create_base_hook_input(permission_mode),
        "hook_event_name": "TaskCompleted",
        "task_id": task_id,
        "task_subject": task_subject,
        "task_description": task_description,
        "teammate_name": teammate_name,
        "team_name": team_name,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=str(uuid.uuid4()),
        signal=signal,
        timeout_ms=timeout_ms,
        tool_use_context=tool_use_context,
    ):
        yield result


async def execute_user_prompt_submit_hooks(
    prompt: str,
    permission_mode: str,
    tool_use_context: Any,
    request_prompt: Any = None,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute UserPromptSubmit hooks."""
    app_state = tool_use_context.get_app_state() if tool_use_context else None
    session_id = getattr(tool_use_context, "agent_id", None) or _get_session_id()
    if not _has_hook_for_event("UserPromptSubmit", app_state, session_id):
        return

    hook_input = {
        **_create_base_hook_input(permission_mode),
        "hook_event_name": "UserPromptSubmit",
        "prompt": prompt,
    }

    abort_signal = getattr(getattr(tool_use_context, "abort_controller", None), "signal", None)

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=str(uuid.uuid4()),
        signal=abort_signal,
        timeout_ms=TOOL_HOOK_EXECUTION_TIMEOUT_MS,
        tool_use_context=tool_use_context,
        request_prompt=request_prompt,
    ):
        yield result


async def execute_session_start_hooks(
    source: Literal["startup", "resume", "clear", "compact"],
    session_id: Optional[str] = None,
    agent_type: Optional[str] = None,
    model: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    force_sync_execution: bool = False,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute SessionStart hooks."""
    hook_input = {
        **_create_base_hook_input(None, session_id),
        "hook_event_name": "SessionStart",
        "source": source,
        "agent_type": agent_type,
        "model": model,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=str(uuid.uuid4()),
        match_query=source,
        signal=signal,
        timeout_ms=timeout_ms,
        force_sync_execution=force_sync_execution,
    ):
        yield result


async def execute_setup_hooks(
    trigger: Literal["init", "maintenance"],
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    force_sync_execution: bool = False,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute Setup hooks."""
    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "Setup",
        "trigger": trigger,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=str(uuid.uuid4()),
        match_query=trigger,
        signal=signal,
        timeout_ms=timeout_ms,
        force_sync_execution=force_sync_execution,
    ):
        yield result


async def execute_subagent_start_hooks(
    agent_id: str,
    agent_type: str,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute SubagentStart hooks."""
    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "SubagentStart",
        "agent_id": agent_id,
        "agent_type": agent_type,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=str(uuid.uuid4()),
        match_query=agent_type,
        signal=signal,
        timeout_ms=timeout_ms,
    ):
        yield result


async def execute_pre_compact_hooks(
    compact_data: Dict[str, Any],
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> Dict[str, Optional[str]]:
    """Execute PreCompact hooks. Returns {new_custom_instructions, user_display_message}."""
    trigger = compact_data.get("trigger", "manual")
    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "PreCompact",
        "trigger": trigger,
        "custom_instructions": compact_data.get("customInstructions"),
    }

    results = await _execute_hooks_outside_repl(
        hook_input=hook_input,
        match_query=trigger,
        signal=signal,
        timeout_ms=timeout_ms,
    )

    if not results:
        return {}

    successful_outputs = [
        r.output.strip() for r in results if r.succeeded and r.output.strip()
    ]

    display_messages: List[str] = []
    for r in results:
        if r.succeeded:
            if r.output.strip():
                display_messages.append(f"PreCompact [{r.command}] completed successfully: {r.output.strip()}")
            else:
                display_messages.append(f"PreCompact [{r.command}] completed successfully")
        else:
            if r.output.strip():
                display_messages.append(f"PreCompact [{r.command}] failed: {r.output.strip()}")
            else:
                display_messages.append(f"PreCompact [{r.command}] failed")

    return {
        "new_custom_instructions": "\n\n".join(successful_outputs) if successful_outputs else None,
        "user_display_message": "\n".join(display_messages) if display_messages else None,
    }


async def execute_post_compact_hooks(
    compact_data: Dict[str, Any],
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> Dict[str, Optional[str]]:
    """Execute PostCompact hooks. Returns {user_display_message}."""
    trigger = compact_data.get("trigger", "manual")
    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "PostCompact",
        "trigger": trigger,
        "compact_summary": compact_data.get("compactSummary", ""),
    }

    results = await _execute_hooks_outside_repl(
        hook_input=hook_input,
        match_query=trigger,
        signal=signal,
        timeout_ms=timeout_ms,
    )

    if not results:
        return {}

    display_messages: List[str] = []
    for r in results:
        if r.succeeded:
            if r.output.strip():
                display_messages.append(f"PostCompact [{r.command}] completed successfully: {r.output.strip()}")
            else:
                display_messages.append(f"PostCompact [{r.command}] completed successfully")
        else:
            if r.output.strip():
                display_messages.append(f"PostCompact [{r.command}] failed: {r.output.strip()}")
            else:
                display_messages.append(f"PostCompact [{r.command}] failed")

    return {"user_display_message": "\n".join(display_messages) if display_messages else None}


async def execute_session_end_hooks(
    reason: str,
    options: Optional[Dict[str, Any]] = None,
) -> None:
    """Execute SessionEnd hooks."""
    opts = options or {}
    get_app_state = opts.get("get_app_state")
    set_app_state = opts.get("set_app_state")
    signal = opts.get("signal")
    timeout_ms = opts.get("timeout_ms", TOOL_HOOK_EXECUTION_TIMEOUT_MS)

    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "SessionEnd",
        "reason": reason,
    }

    results = await _execute_hooks_outside_repl(
        get_app_state=get_app_state,
        hook_input=hook_input,
        match_query=reason,
        signal=signal,
        timeout_ms=timeout_ms,
    )

    for r in results:
        if not r.succeeded and r.output:
            sys.stderr.write(f"SessionEnd hook [{r.command}] failed: {r.output}\n")

    if set_app_state:
        session_id = _get_session_id()
        _clear_session_hooks(set_app_state, session_id)


async def execute_permission_request_hooks(
    tool_name: str,
    tool_use_id: str,
    tool_input: Any,
    tool_use_context: Any,
    permission_mode: Optional[str] = None,
    permission_suggestions: Optional[List[Any]] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    request_prompt: Any = None,
    tool_input_summary: Optional[str] = None,
) -> AsyncGenerator[AggregatedHookResult, None]:
    """Execute PermissionRequest hooks."""
    hook_input = {
        **_create_base_hook_input(permission_mode, None, tool_use_context),
        "hook_event_name": "PermissionRequest",
        "tool_name": tool_name,
        "tool_input": tool_input,
        "permission_suggestions": permission_suggestions,
    }

    async for result in _execute_hooks(
        hook_input=hook_input,
        tool_use_id=tool_use_id,
        match_query=tool_name,
        signal=signal,
        timeout_ms=timeout_ms,
        tool_use_context=tool_use_context,
        request_prompt=request_prompt,
        tool_input_summary=tool_input_summary,
    ):
        yield result


# ConfigChangeSource type alias
ConfigChangeSource = Literal[
    "user_settings",
    "project_settings",
    "local_settings",
    "policy_settings",
    "skills",
]


async def execute_config_change_hooks(
    source: ConfigChangeSource,
    file_path: Optional[str] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> List[HookOutsideReplResult]:
    """Execute ConfigChange hooks."""
    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "ConfigChange",
        "source": source,
        "file_path": file_path,
    }

    results = await _execute_hooks_outside_repl(
        hook_input=hook_input,
        timeout_ms=timeout_ms,
        match_query=source,
    )

    # Policy settings cannot block changes
    if source == "policy_settings":
        return [HookOutsideReplResult(
            command=r.command,
            succeeded=r.succeeded,
            output=r.output,
            blocked=False,
            watch_paths=r.watch_paths,
            system_message=r.system_message,
        ) for r in results]

    return results


async def _execute_env_hooks(
    hook_input: Dict[str, Any],
    timeout_ms: int,
) -> Dict[str, Any]:
    """Execute env-related hooks (CwdChanged, FileChanged)."""
    results = await _execute_hooks_outside_repl(hook_input=hook_input, timeout_ms=timeout_ms)
    if results:
        _invalidate_session_env_cache()
    watch_paths = [p for r in results for p in (r.watch_paths or [])]
    system_messages = [r.system_message for r in results if r.system_message]
    return {"results": results, "watch_paths": watch_paths, "system_messages": system_messages}


async def execute_cwd_changed_hooks(
    old_cwd: str,
    new_cwd: str,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> Dict[str, Any]:
    """Execute CwdChanged hooks."""
    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "CwdChanged",
        "old_cwd": old_cwd,
        "new_cwd": new_cwd,
    }
    return await _execute_env_hooks(hook_input, timeout_ms)


async def execute_file_changed_hooks(
    file_path: str,
    event: Literal["change", "add", "unlink"],
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
) -> Dict[str, Any]:
    """Execute FileChanged hooks."""
    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "FileChanged",
        "file_path": file_path,
        "event": event,
    }
    return await _execute_env_hooks(hook_input, timeout_ms)


# InstructionsLoadReason / InstructionsMemoryType
InstructionsLoadReason = Literal[
    "session_start", "nested_traversal", "path_glob_match", "include", "compact"
]
InstructionsMemoryType = Literal["User", "Project", "Local", "Managed"]


def has_instructions_loaded_hook() -> bool:
    """Check if InstructionsLoaded hooks are configured."""
    snapshot_hooks = _get_hooks_config_from_snapshot()
    if snapshot_hooks and snapshot_hooks.get("InstructionsLoaded"):
        return True
    registered = _get_registered_hooks()
    if registered and registered.get("InstructionsLoaded"):
        return True
    return False


async def execute_instructions_loaded_hooks(
    file_path: str,
    memory_type: InstructionsMemoryType,
    load_reason: InstructionsLoadReason,
    options: Optional[Dict[str, Any]] = None,
) -> None:
    """Execute InstructionsLoaded hooks (fire-and-forget)."""
    opts = options or {}
    timeout_ms = opts.get("timeout_ms", TOOL_HOOK_EXECUTION_TIMEOUT_MS)

    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "InstructionsLoaded",
        "file_path": file_path,
        "memory_type": memory_type,
        "load_reason": load_reason,
        "globs": opts.get("globs"),
        "trigger_file_path": opts.get("trigger_file_path"),
        "parent_file_path": opts.get("parent_file_path"),
    }

    await _execute_hooks_outside_repl(
        hook_input=hook_input,
        timeout_ms=timeout_ms,
        match_query=load_reason,
    )


# ---------------------------------------------------------------------------
# _parse_elicitation_hook_output
# ---------------------------------------------------------------------------

def _parse_elicitation_hook_output(
    result: HookOutsideReplResult,
    expected_event_name: Literal["Elicitation", "ElicitationResult"],
) -> Dict[str, Any]:
    """Parse elicitation-specific fields from an outside-REPL hook result."""
    # Exit code 2 / blocked = blocking error
    if result.blocked and not result.succeeded:
        return {
            "blocking_error": HookBlockingError(
                blocking_error=result.output or "Elicitation blocked by hook",
                command=result.command,
            )
        }

    if not result.output.strip():
        return {}

    trimmed = result.output.strip()
    if not trimmed.startswith("{"):
        return {}

    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError:
        return {}

    if _is_async_hook_json_output(parsed):
        return {}

    if not _is_sync_hook_json_output(parsed):
        return {}

    # Top-level block decision
    if parsed.get("decision") == "block" or result.blocked:
        return {
            "blocking_error": HookBlockingError(
                blocking_error=parsed.get("reason") or "Elicitation blocked by hook",
                command=result.command,
            )
        }

    specific = parsed.get("hookSpecificOutput") or parsed.get("hook_specific_output")
    if not specific or specific.get("hookEventName") != expected_event_name:
        return {}

    action = specific.get("action")
    if not action:
        return {}

    response = ElicitationResponse(
        action=action,
        content=specific.get("content"),
    )

    out: Dict[str, Any] = {"response": response}

    if action == "decline":
        out["blocking_error"] = HookBlockingError(
            blocking_error=parsed.get("reason") or (
                "Elicitation denied by hook"
                if expected_event_name == "Elicitation"
                else "Elicitation result blocked by hook"
            ),
            command=result.command,
        )

    return out


async def execute_elicitation_hooks(
    *,
    server_name: str,
    message: str,
    requested_schema: Optional[Dict[str, Any]] = None,
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    mode: Optional[str] = None,
    url: Optional[str] = None,
    elicitation_id: Optional[str] = None,
) -> ElicitationHookResult:
    """Execute Elicitation hooks."""
    hook_input = {
        **_create_base_hook_input(permission_mode),
        "hook_event_name": "Elicitation",
        "mcp_server_name": server_name,
        "message": message,
        "mode": mode,
        "url": url,
        "elicitation_id": elicitation_id,
        "requested_schema": requested_schema,
    }

    results = await _execute_hooks_outside_repl(
        hook_input=hook_input,
        match_query=server_name,
        signal=signal,
        timeout_ms=timeout_ms,
    )

    elicitation_response: Optional[ElicitationResponse] = None
    blocking_error: Optional[HookBlockingError] = None

    for result in results:
        parsed = _parse_elicitation_hook_output(result, "Elicitation")
        if parsed.get("blocking_error"):
            blocking_error = parsed["blocking_error"]
        if parsed.get("response"):
            elicitation_response = parsed["response"]

    return ElicitationHookResult(
        elicitation_response=elicitation_response,
        blocking_error=blocking_error,
    )


async def execute_elicitation_result_hooks(
    *,
    server_name: str,
    action: Literal["accept", "decline", "cancel"],
    content: Optional[Dict[str, Any]] = None,
    permission_mode: Optional[str] = None,
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    mode: Optional[str] = None,
    elicitation_id: Optional[str] = None,
) -> ElicitationResultHookResult:
    """Execute ElicitationResult hooks."""
    hook_input = {
        **_create_base_hook_input(permission_mode),
        "hook_event_name": "ElicitationResult",
        "mcp_server_name": server_name,
        "elicitation_id": elicitation_id,
        "mode": mode,
        "action": action,
        "content": content,
    }

    results = await _execute_hooks_outside_repl(
        hook_input=hook_input,
        match_query=server_name,
        signal=signal,
        timeout_ms=timeout_ms,
    )

    elicitation_result_response: Optional[ElicitationResponse] = None
    blocking_error: Optional[HookBlockingError] = None

    for result in results:
        parsed = _parse_elicitation_hook_output(result, "ElicitationResult")
        if parsed.get("blocking_error"):
            blocking_error = parsed["blocking_error"]
        if parsed.get("response"):
            elicitation_result_response = parsed["response"]

    return ElicitationResultHookResult(
        elicitation_result_response=elicitation_result_response,
        blocking_error=blocking_error,
    )


async def execute_status_line_command(
    status_line_input: Dict[str, Any],
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = 5000,
    log_result: bool = False,
) -> Optional[str]:
    """Execute the StatusLine command hook. Returns the status text or None."""
    if _should_disable_all_hooks():
        return None
    if _should_skip_hook_due_to_trust():
        return None

    if _should_allow_managed_hooks_only():
        settings = _get_settings_for_source("policySettings")
    else:
        settings = _get_settings_deprecated()

    if not settings:
        return None

    status_line = settings.get("statusLine")
    if not status_line or status_line.get("type") != "command":
        return None

    abort_signal = signal or asyncio.Event()

    try:
        json_input = json.dumps(status_line_input, default=str)
        hook = {"type": "command", "command": status_line.get("command", "")}
        result = await _exec_command_hook(
            hook=hook,
            hook_event="StatusLine",
            hook_name="statusLine",
            json_input=json_input,
            abort_signal=abort_signal,
            hook_id=str(uuid.uuid4()),
            timeout_ms=timeout_ms,
        )

        if result.get("aborted"):
            return None

        if result.get("status") == 0:
            output = "\n".join(
                line.strip()
                for line in result.get("stdout", "").strip().splitlines()
                if line.strip()
            )
            if output:
                if log_result:
                    _log_debug(f"StatusLine [{status_line.get('command')}] completed with status 0")
                return output
        elif log_result:
            _log_debug(
                f"StatusLine [{status_line.get('command')}] completed with status {result.get('status')}",
                level="warn",
            )

        return None
    except Exception as exc:
        _log_debug(f"Status hook failed: {exc}", level="error")
        return None


async def execute_file_suggestion_command(
    file_suggestion_input: Dict[str, Any],
    signal: Optional[asyncio.Event] = None,
    timeout_ms: int = 5000,
) -> List[str]:
    """Execute the FileSuggestion command hook. Returns list of file paths."""
    if _should_disable_all_hooks():
        return []
    if _should_skip_hook_due_to_trust():
        return []

    if _should_allow_managed_hooks_only():
        settings = _get_settings_for_source("policySettings")
    else:
        settings = _get_settings_deprecated()

    if not settings:
        return []

    file_suggestion = settings.get("fileSuggestion")
    if not file_suggestion or file_suggestion.get("type") != "command":
        return []

    abort_signal = signal or asyncio.Event()

    try:
        json_input = json.dumps(file_suggestion_input, default=str)
        hook = {"type": "command", "command": file_suggestion.get("command", "")}
        result = await _exec_command_hook(
            hook=hook,
            hook_event="FileSuggestion",
            hook_name="FileSuggestion",
            json_input=json_input,
            abort_signal=abort_signal,
            hook_id=str(uuid.uuid4()),
            timeout_ms=timeout_ms,
        )

        if result.get("aborted") or result.get("status") != 0:
            return []

        return [
            line.strip()
            for line in result.get("stdout", "").splitlines()
            if line.strip()
        ]
    except Exception as exc:
        _log_debug(f"File suggestion helper failed: {exc}", level="error")
        return []


# ---------------------------------------------------------------------------
# Worktree hooks
# ---------------------------------------------------------------------------


def has_worktree_create_hook() -> bool:
    """Return True if WorktreeCreate hooks are configured."""
    snapshot_hooks = _get_hooks_config_from_snapshot()
    if snapshot_hooks and snapshot_hooks.get("WorktreeCreate"):
        return True
    registered = _get_registered_hooks()
    if not registered or not registered.get("WorktreeCreate"):
        return False
    managed_only = _should_allow_managed_hooks_only()
    return any(
        not (managed_only and "plugin_root" in m)
        for m in registered["WorktreeCreate"]
    )


async def execute_worktree_create_hook(name: str) -> Dict[str, str]:
    """
    Execute WorktreeCreate hooks.
    Returns {'worktree_path': <path>}. Raises on failure.
    """
    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "WorktreeCreate",
        "name": name,
    }

    results = await _execute_hooks_outside_repl(
        hook_input=hook_input,
        timeout_ms=TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    )

    successful = next(
        (r for r in results if r.succeeded and r.output.strip()),
        None,
    )

    if not successful:
        failed_outputs = [
            f"{r.command}: {r.output.strip() or 'no output'}"
            for r in results
            if not r.succeeded
        ]
        raise RuntimeError(
            f"WorktreeCreate hook failed: {'; '.join(failed_outputs) or 'no successful output'}"
        )

    return {"worktree_path": successful.output.strip()}


async def execute_worktree_remove_hook(worktree_path: str) -> bool:
    """
    Execute WorktreeRemove hooks.
    Returns True if hooks ran, False if none configured.
    """
    snapshot_hooks = _get_hooks_config_from_snapshot()
    registered = _get_registered_hooks()
    has_snapshot = bool(snapshot_hooks and snapshot_hooks.get("WorktreeRemove"))
    has_registered = bool(registered and registered.get("WorktreeRemove"))

    if not has_snapshot and not has_registered:
        return False

    hook_input = {
        **_create_base_hook_input(),
        "hook_event_name": "WorktreeRemove",
        "worktree_path": worktree_path,
    }

    results = await _execute_hooks_outside_repl(
        hook_input=hook_input,
        timeout_ms=TOOL_HOOK_EXECUTION_TIMEOUT_MS,
    )

    if not results:
        return False

    for r in results:
        if not r.succeeded:
            _log_debug(
                f"WorktreeRemove hook failed [{r.command}]: {r.output.strip()}",
                level="error",
            )

    return True


# ---------------------------------------------------------------------------
# __all__
# ---------------------------------------------------------------------------

__all__ = [
    # Types
    "HookBlockingError",
    "HookOutsideReplResult",
    "ElicitationResponse",
    "ElicitationHookResult",
    "ElicitationResultHookResult",
    "AggregatedHookResult",
    "ConfigChangeSource",
    "InstructionsLoadReason",
    "InstructionsMemoryType",
    # Utilities
    "has_blocking_result",
    "get_pre_tool_hook_blocking_message",
    "get_stop_hook_message",
    "get_teammate_idle_hook_message",
    "get_task_created_hook_message",
    "get_task_completed_hook_message",
    "get_user_prompt_submit_hook_blocking_message",
    # Execute functions
    "execute_pre_tool_hooks",
    "execute_post_tool_hooks",
    "execute_post_tool_use_failure_hooks",
    "execute_permission_denied_hooks",
    "execute_notification_hooks",
    "execute_stop_failure_hooks",
    "execute_stop_hooks",
    "execute_teammate_idle_hooks",
    "execute_task_created_hooks",
    "execute_task_completed_hooks",
    "execute_user_prompt_submit_hooks",
    "execute_session_start_hooks",
    "execute_setup_hooks",
    "execute_subagent_start_hooks",
    "execute_pre_compact_hooks",
    "execute_post_compact_hooks",
    "execute_session_end_hooks",
    "execute_permission_request_hooks",
    "execute_config_change_hooks",
    "execute_cwd_changed_hooks",
    "execute_file_changed_hooks",
    "execute_instructions_loaded_hooks",
    "execute_elicitation_hooks",
    "execute_elicitation_result_hooks",
    "execute_status_line_command",
    "execute_file_suggestion_command",
    "has_worktree_create_hook",
    "execute_worktree_create_hook",
    "execute_worktree_remove_hook",
    "has_instructions_loaded_hook",
    "TOOL_HOOK_EXECUTION_TIMEOUT_MS",
]

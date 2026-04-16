"""
Core query loop — sends user messages to the API and handles tool use.
Ported from query.ts (1729 lines → core loop, streaming).

Key features over the basic implementation:
- Extended thinking / thinking blocks support
- stop_reason handling: tool_use / end_turn / pause_turn / max_tokens
- Error recovery: max_output_tokens retry, overloaded (529), rate-limit (429)
- Compact boundary support (getMessagesAfterCompactBoundary)
- Pre/post tool hooks
- is_error field on tool_result
- Interruption (AbortController-style via asyncio.Event)
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, TypedDict

logger = logging.getLogger(__name__)

MAX_TOOL_ITERATIONS = 50
MAX_OUTPUT_TOKENS_RECOVERY_LIMIT = 3

# ─────────────────────────────────────────────────────────────────────────────
# TypedDicts
# ─────────────────────────────────────────────────────────────────────────────

class QueryParams(TypedDict, total=False):
    # Basic model params
    model: str
    max_tokens: int
    system_prompt: List[str]
    tools: List[Any]
    source: str
    is_non_interactive: bool

    # Permission / context
    permission_context: Any
    tool_use_context: Any
    signal: Any                     # asyncio.Event for cancellation

    # Extended thinking
    thinking_config: Optional[Dict[str, Any]]

    # Recovery / limits
    max_turns: Optional[int]
    max_output_tokens_override: Optional[int]
    fallback_model: Optional[str]

    # Hooks
    pre_tool_hooks: List[Any]
    post_tool_hooks: List[Any]
    post_sampling_hooks: List[Any]

    # Compact boundary messages in the history
    # (list of dicts with type="compact_boundary")
    messages_with_compact: bool


# ─────────────────────────────────────────────────────────────────────────────
# Public entry-point (backward-compatible signature)
# ─────────────────────────────────────────────────────────────────────────────

async def query(
    messages: List[dict],
    params: Optional[QueryParams] = None,
    signal: Any = None,
) -> AsyncIterator[dict]:
    """
    Core streaming query loop.

    Yields dicts with a ``type`` key:
      request_start, thinking, assistant_message, tool_use, tool_result,
      user_interruption, error, final_response, system, max_iterations_reached
    """
    opts = params or {}
    # Allow signal in either params or as positional arg
    effective_signal = signal or opts.get("signal")

    async for event in _query_loop(messages, opts, effective_signal):
        yield event


# ─────────────────────────────────────────────────────────────────────────────
# Internal loop state
# ─────────────────────────────────────────────────────────────────────────────

class _LoopState:
    """Mutable state carried between query loop iterations."""

    __slots__ = (
        "messages",
        "max_output_tokens_recovery_count",
        "max_output_tokens_override",
        "turn_count",
        "transition",
    )

    def __init__(
        self,
        messages: List[dict],
        max_output_tokens_override: Optional[int] = None,
    ) -> None:
        self.messages = messages
        self.max_output_tokens_recovery_count = 0
        self.max_output_tokens_override = max_output_tokens_override
        self.turn_count = 1
        self.transition: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Main loop
# ─────────────────────────────────────────────────────────────────────────────

async def _query_loop(
    initial_messages: List[dict],
    opts: QueryParams,
    signal: Any,
) -> AsyncIterator[dict]:
    """Async generator implementing the agentic query loop."""
    model = opts.get("model")
    max_tokens = opts.get("max_tokens", 4096)
    system_prompt = opts.get("system_prompt", [])
    tools_list = opts.get("tools", [])
    source = opts.get("source", "repl_main_thread")
    permission_ctx = opts.get("permission_context")
    thinking_config = opts.get("thinking_config")
    max_turns = opts.get("max_turns")
    pre_tool_hooks = opts.get("pre_tool_hooks") or []
    post_tool_hooks = opts.get("post_tool_hooks") or []
    post_sampling_hooks = opts.get("post_sampling_hooks") or []

    state = _LoopState(
        messages=list(initial_messages),
        max_output_tokens_override=opts.get("max_output_tokens_override"),
    )

    yield {"type": "request_start", "model": model, "source": source}

    iteration = 0

    while True:
        if max_turns is not None and state.turn_count > max_turns:
            yield {"type": "max_turns_reached", "turn_count": state.turn_count}
            return

        iteration += 1
        if iteration > MAX_TOOL_ITERATIONS:
            yield {"type": "max_iterations_reached", "iterations": iteration}
            return

        # ── Check for abort ──────────────────────────────────────────────────
        if _is_aborted(signal):
            yield {"type": "user_interruption"}
            return

        # ── Get messages after compact boundary ──────────────────────────────
        messages_for_query = get_messages_after_compact_boundary(state.messages)

        # ── Serialize tools ──────────────────────────────────────────────────
        serialized_tools = _serialize_tools(tools_list)

        # ── Call model ───────────────────────────────────────────────────────
        try:
            result = await _call_model_with_retry(
                messages=messages_for_query,
                system_prompt=system_prompt,
                tools=serialized_tools or None,
                model=model,
                max_tokens=state.max_output_tokens_override or max_tokens,
                thinking_config=thinking_config,
                source=source,
                signal=signal,
            )
        except asyncio.CancelledError:
            yield {"type": "user_interruption"}
            return
        except Exception as e:
            error_msg = str(e)
            yield {"type": "error", "error": error_msg}
            return

        # ── Parse response ───────────────────────────────────────────────────
        content = result.get("content", [])
        stop_reason = result.get("stop_reason")
        usage = result.get("usage", {})

        # Track costs
        try:
            from claude_code.cost_tracker import add_usage
            add_usage(usage, model=model or "")
        except Exception:
            pass

        # ── Yield thinking blocks ────────────────────────────────────────────
        for block in content:
            if isinstance(block, dict) and block.get("type") in ("thinking", "redacted_thinking"):
                yield {
                    "type": "thinking",
                    "thinking_type": block.get("type"),
                    "thinking": block.get("thinking") or block.get("data", ""),
                }

        # ── Yield assistant message ──────────────────────────────────────────
        assistant_msg = {
            "type": "assistant_message",
            "content": content,
            "stop_reason": stop_reason,
            "usage": usage,
            "iteration": iteration,
        }

        # Handle max_output_tokens (withheld recovery, mirroring TS)
        is_max_tokens_error = stop_reason == "max_tokens"

        if not is_max_tokens_error:
            yield assistant_msg

        # ── Post-sampling hooks ──────────────────────────────────────────────
        for hook in post_sampling_hooks:
            try:
                hook_fn = getattr(hook, "on_assistant_message", None)
                if callable(hook_fn):
                    await _maybe_await(hook_fn(assistant_msg))
            except Exception as hook_err:
                logger.debug("post_sampling hook error: %s", hook_err)

        # ── Abort check after streaming ──────────────────────────────────────
        if _is_aborted(signal):
            yield {"type": "user_interruption", "tool_use": False}
            return

        # ── Extract tool use blocks ──────────────────────────────────────────
        tool_use_blocks = [
            b for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]
        needs_follow_up = bool(tool_use_blocks)

        # ── Handle stop reasons ──────────────────────────────────────────────
        if stop_reason == "pause_turn":
            # Model has paused — surface and stop
            if not is_max_tokens_error:
                pass  # already yielded
            yield {"type": "paused", "content": content}
            return

        if stop_reason == "max_tokens" or is_max_tokens_error:
            if state.max_output_tokens_recovery_count < MAX_OUTPUT_TOKENS_RECOVERY_LIMIT:
                # Recovery: inject continuation message and retry
                state.max_output_tokens_recovery_count += 1
                recovery_content = (
                    "Output token limit hit. Resume directly — no apology, no recap of what you were doing. "
                    "Pick up mid-thought if that is where the cut happened. Break remaining work into smaller pieces."
                )
                state.messages = list(state.messages) + [
                    {"role": "assistant", "content": content},
                    {"role": "user", "content": [{"type": "text", "text": recovery_content}]},
                ]
                state.transition = "max_output_tokens_recovery"
                continue
            else:
                # Recovery exhausted — surface the error
                yield assistant_msg
                yield {"type": "final_response", "content": content, "iterations": iteration, "usage": usage, "stop_reason": stop_reason}
                return

        if not needs_follow_up:
            # end_turn or no tool calls
            yield {
                "type": "final_response",
                "content": content,
                "iterations": iteration,
                "usage": usage,
                "stop_reason": stop_reason,
            }
            return

        # ── Execute tools ────────────────────────────────────────────────────
        tool_results = []

        for tu in tool_use_blocks:
            tool_name = tu.get("name", "")
            tool_input = tu.get("input", {})
            tool_use_id = tu.get("id", "")

            yield {
                "type": "tool_use",
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_use_id": tool_use_id,
            }

            # ── Pre-tool hooks ───────────────────────────────────────────────
            for hook in pre_tool_hooks:
                try:
                    hook_fn = getattr(hook, "before_tool", None)
                    if callable(hook_fn):
                        await _maybe_await(hook_fn(tool_name, tool_input, tool_use_id))
                except Exception as hook_err:
                    logger.debug("pre_tool hook error: %s", hook_err)

            # ── Permission check ─────────────────────────────────────────────
            can_use, is_perm_error = await _check_permission_with_error(
                tool_name, tool_input, permission_ctx
            )

            is_error = False
            if not can_use:
                result_content = f"Permission denied for tool: {tool_name}"
                is_error = True
                yield {"type": "permission_denied", "tool_name": tool_name}
            else:
                try:
                    result_content = await _execute_tool(
                        tool_name, tool_input, tools_list, permission_ctx
                    )
                except asyncio.CancelledError:
                    yield {"type": "user_interruption"}
                    return
                except Exception as e:
                    result_content = f"Error executing {tool_name}: {e}"
                    is_error = True

            # ── Post-tool hooks ──────────────────────────────────────────────
            for hook in post_tool_hooks:
                try:
                    hook_fn = getattr(hook, "after_tool", None)
                    if callable(hook_fn):
                        await _maybe_await(hook_fn(tool_name, tool_input, tool_use_id, result_content, is_error))
                except Exception as hook_err:
                    logger.debug("post_tool hook error: %s", hook_err)

            yield {
                "type": "tool_result",
                "tool_name": tool_name,
                "tool_use_id": tool_use_id,
                "result": result_content,
                "is_error": is_error,
            }

            # Build tool_result block for API
            tool_result_block: dict = {
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": str(result_content) if not isinstance(result_content, str) else result_content,
            }
            if is_error:
                tool_result_block["is_error"] = True

            tool_results.append(tool_result_block)

        # ── Append to conversation history ───────────────────────────────────
        state.messages = list(state.messages) + [
            {"role": "assistant", "content": content},
            {"role": "user", "content": tool_results},
        ]
        state.turn_count += 1
        state.max_output_tokens_recovery_count = 0
        state.transition = "tool_use"


# ─────────────────────────────────────────────────────────────────────────────
# Model call with retry (overloaded / rate-limit)
# ─────────────────────────────────────────────────────────────────────────────

async def _call_model_with_retry(
    messages: List[dict],
    system_prompt: List[str],
    tools: Optional[List[dict]],
    model: Optional[str],
    max_tokens: int,
    thinking_config: Optional[dict],
    source: str,
    signal: Any,
    max_retries: int = 3,
) -> dict:
    """
    Call the model, retrying on 429 / 529 with exponential back-off.
    Mirrors the TS with_retry.ts behaviour.
    """
    from claude_code.services.api.claude import query_model_without_streaming

    delay = 1.0
    last_exc: Optional[Exception] = None

    for attempt in range(max_retries + 1):
        if _is_aborted(signal):
            raise asyncio.CancelledError()

        try:
            result = await query_model_without_streaming(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                options={
                    "model": model,
                    "max_tokens": max_tokens,
                    "source": source,
                    **({"thinking_config": thinking_config} if thinking_config else {}),
                },
                signal=signal,
            )
            return result
        except Exception as exc:
            last_exc = exc
            err_str = str(exc)
            status = _extract_status_code(exc)

            # Overloaded (529) or rate-limit (429) → retry
            if status in (429, 529) and attempt < max_retries:
                retry_delay = delay * (2 ** attempt)
                logger.debug(
                    "API %s error, retrying in %.1fs (attempt %d/%d)",
                    status, retry_delay, attempt + 1, max_retries,
                )
                await asyncio.sleep(retry_delay)
                continue

            raise

    raise last_exc  # type: ignore[misc]


def _extract_status_code(exc: Exception) -> Optional[int]:
    """Try to extract an HTTP status code from an exception."""
    for attr in ("status_code", "status", "code"):
        val = getattr(exc, attr, None)
        if isinstance(val, int):
            return val
    # Try parsing from message string
    msg = str(exc)
    for code in (429, 529, 500, 503):
        if str(code) in msg:
            return code
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Compact boundary helper
# ─────────────────────────────────────────────────────────────────────────────

def get_messages_after_compact_boundary(messages: List[dict]) -> List[dict]:
    """
    Return only the messages AFTER the last compact_boundary marker.
    Mirrors getMessagesAfterCompactBoundary in messages.ts.
    """
    last_boundary = -1
    for i, msg in enumerate(messages):
        msg_type = msg.get("type", "")
        # Check both top-level type and nested message type
        if msg_type == "compact_boundary":
            last_boundary = i
        elif msg_type == "system" and msg.get("subtype") == "compact_boundary":
            last_boundary = i

    if last_boundary == -1:
        return list(messages)
    return list(messages[last_boundary + 1:])


# ─────────────────────────────────────────────────────────────────────────────
# Permission helpers
# ─────────────────────────────────────────────────────────────────────────────

async def _check_permission(
    tool_name: str, tool_input: dict, permission_ctx: Any
) -> bool:
    """Check if tool use is allowed. Returns True by default."""
    allowed, _ = await _check_permission_with_error(tool_name, tool_input, permission_ctx)
    return allowed


async def _check_permission_with_error(
    tool_name: str, tool_input: dict, permission_ctx: Any
) -> tuple[bool, bool]:
    """Returns (is_allowed, is_permission_error)."""
    if permission_ctx is None:
        return True, False
    check_fn = getattr(permission_ctx, "can_use_tool", None)
    if callable(check_fn):
        try:
            result = check_fn(tool_name, tool_input)
            if asyncio.iscoroutine(result):
                result = await result
            return bool(result), False
        except Exception:
            return False, True
    return True, False


# ─────────────────────────────────────────────────────────────────────────────
# Tool execution
# ─────────────────────────────────────────────────────────────────────────────

async def _execute_tool(
    tool_name: str,
    tool_input: dict,
    tools_list: List[Any],
    context: Any,
) -> Any:
    """Find and execute a tool by name."""
    for t in tools_list:
        if getattr(t, "name", None) == tool_name:
            call_fn = getattr(t, "call", None)
            if callable(call_fn):
                result = call_fn(tool_input, context)
                if asyncio.iscoroutine(result):
                    result = await result
                return result
    return f"Tool not found: {tool_name}"


# ─────────────────────────────────────────────────────────────────────────────
# Tool serialization
# ─────────────────────────────────────────────────────────────────────────────

def _serialize_tools(tools: List[Any]) -> List[dict]:
    """Convert tool objects to API-compatible dicts."""
    result = []
    for t in tools:
        if isinstance(t, dict):
            result.append(t)
            continue
        schema_fn = getattr(t, "input_schema", None)
        schema = schema_fn() if callable(schema_fn) else {"type": "object", "properties": {}}
        result.append({
            "name": getattr(t, "name", "unknown"),
            "description": getattr(t, "description", ""),
            "input_schema": schema,
        })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Utilities
# ─────────────────────────────────────────────────────────────────────────────

def _is_aborted(signal: Any) -> bool:
    """Check if an abort signal has been set."""
    if signal is None:
        return False
    if isinstance(signal, asyncio.Event):
        return signal.is_set()
    if callable(getattr(signal, "is_set", None)):
        return signal.is_set()
    if hasattr(signal, "aborted"):
        return bool(signal.aborted)
    return False


async def _maybe_await(value: Any) -> Any:
    """Await a coroutine if necessary, otherwise return as-is."""
    if asyncio.iscoroutine(value):
        return await value
    return value

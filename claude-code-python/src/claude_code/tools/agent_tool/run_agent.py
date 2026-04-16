"""
Core agent run loop.
Ported from AgentTool/runAgent.ts (973 lines → complete implementation).

Key exports:
- run_agent(...)                  — async generator, full agent execution loop
- filter_incomplete_tool_calls()  — filter orphaned tool_use blocks
- get_agent_system_prompt()       — build agent system prompt with env details
"""
from __future__ import annotations

import asyncio
import logging
import uuid as _uuid_mod
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Set,
)

logger = logging.getLogger(__name__)

# Default maximum agent turns, mirrors TS DEFAULT_MAX_TURNS fallback
DEFAULT_MAX_AGENT_TURNS = 50


# ---------------------------------------------------------------------------
# Public: run_agent()
# ---------------------------------------------------------------------------

async def run_agent(
    *,
    agent_definition: Any,
    prompt_messages: List[dict],
    tool_use_context: Any = None,
    can_use_tool: Any = None,
    is_async: bool = False,
    can_show_permission_prompts: Optional[bool] = None,
    fork_context_messages: Optional[List[dict]] = None,
    query_source: str = "agent",
    override: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None,
    max_turns: Optional[int] = None,
    preserve_tool_use_results: bool = False,
    available_tools: Optional[List[Any]] = None,
    allowed_tools: Optional[List[str]] = None,
    on_cache_safe_params: Optional[Callable] = None,
    content_replacement_state: Any = None,
    use_exact_tools: bool = False,
    worktree_path: Optional[str] = None,
    description: Optional[str] = None,
    transcript_subdir: Optional[str] = None,
    on_query_progress: Optional[Callable] = None,
) -> AsyncGenerator[dict, None]:
    """
    Full agent execution loop.

    Mirrors runAgent() in runAgent.ts (lines 248–).

    Yields message dicts with ``type`` key. Notable types:
      - assistant  (from query's assistant_message events)
      - user       (tool results forwarded by query)
      - progress
      - final_response
      - attachment
    """
    from claude_code.query import query, QueryParams
    from claude_code.utils.uuid import create_agent_id
    from claude_code.tools.agent_tool.agent_tool_utils import resolve_agent_tools
    from claude_code.tools.agent_tool.load_agents_dir import is_built_in_agent

    # ------------------------------------------------------------------
    # 1. Resolve agent ID
    # ------------------------------------------------------------------
    override = override or {}
    agent_id: str = override.get("agent_id") or create_agent_id()

    # ------------------------------------------------------------------
    # 2. Resolve model
    # ------------------------------------------------------------------
    resolved_model: Optional[str] = model
    if resolved_model is None:
        # Try agent definition's model first, then context options
        resolved_model = getattr(agent_definition, "model", None)
        if resolved_model is None and tool_use_context is not None:
            opts = getattr(tool_use_context, "options", {})
            resolved_model = (
                opts.get("mainLoopModel") if isinstance(opts, dict)
                else getattr(opts, "main_loop_model", None)
            )

    # ------------------------------------------------------------------
    # 3. Build context messages (handle fork + filter orphans)
    # ------------------------------------------------------------------
    context_messages: List[dict] = []
    if fork_context_messages:
        context_messages = filter_incomplete_tool_calls(fork_context_messages)

    initial_messages: List[dict] = [*context_messages, *prompt_messages]

    # ------------------------------------------------------------------
    # 4. Resolve tools
    # ------------------------------------------------------------------
    tools: List[Any] = available_tools or []
    if not use_exact_tools:
        try:
            result = resolve_agent_tools(
                agent_definition,
                tools,
                is_async=is_async,
            )
            tools = result.resolved_tools
        except Exception as exc:
            logger.debug("resolve_agent_tools failed: %s", exc)

    # ------------------------------------------------------------------
    # 5. Build system prompt
    # ------------------------------------------------------------------
    system_prompt_parts: List[str]
    if override.get("system_prompt"):
        raw = override["system_prompt"]
        system_prompt_parts = raw if isinstance(raw, list) else [raw]
    else:
        system_prompt_parts = await _get_agent_system_prompt(
            agent_definition=agent_definition,
            resolved_model=resolved_model or "",
            tools=tools,
        )

    # ------------------------------------------------------------------
    # 6. Initialize MCP servers (stub — no-op in Python port)
    # ------------------------------------------------------------------
    mcp_cleanup = await _init_agent_mcp_servers_stub(agent_definition)

    # ------------------------------------------------------------------
    # 7. Build query params
    # ------------------------------------------------------------------
    max_agent_turns: Optional[int] = max_turns
    if max_agent_turns is None:
        max_agent_turns = getattr(agent_definition, "max_turns", None)
    if max_agent_turns is None:
        max_agent_turns = DEFAULT_MAX_AGENT_TURNS

    # Determine abort controller / cancellation signal
    abort_event: Optional[asyncio.Event] = None
    if override.get("abort_controller"):
        ctrl = override["abort_controller"]
        abort_event = getattr(ctrl, "_event", None)
    if abort_event is None and tool_use_context is not None:
        abort_event = getattr(tool_use_context, "abort_event", None)
    if abort_event is None and is_async:
        abort_event = asyncio.Event()

    # ------------------------------------------------------------------
    # 8. Build QueryParams for the inner query() call
    # ------------------------------------------------------------------
    params: QueryParams = {
        "source": query_source,
        "system_prompt": system_prompt_parts,
        "tools": tools,
        "max_turns": max_agent_turns,
        "is_non_interactive": is_async,
        "tool_use_context": tool_use_context,
    }
    if resolved_model:
        params["model"] = resolved_model

    # ------------------------------------------------------------------
    # 9. Execute inner query loop, yield messages
    # ------------------------------------------------------------------
    try:
        async for message in query(initial_messages, params, abort_event):
            # Fire progress callback for liveness detection
            if on_query_progress is not None:
                on_query_progress()

            msg_type = message.get("type") if isinstance(message, dict) else None

            # Skip raw stream events (stream_event) — forward only recordable types
            if msg_type == "stream_event":
                continue

            # Bubble up attachment (e.g., max_turns_reached signal)
            if msg_type == "attachment":
                attachment = message.get("attachment", {})
                if isinstance(attachment, dict) and attachment.get("type") == "max_turns_reached":
                    logger.debug(
                        "[Agent: %s] Reached max turns limit (%s)",
                        getattr(agent_definition, "agent_type", "?"),
                        attachment.get("maxTurns"),
                    )
                    break
                yield message
                continue

            # Yield recordable messages: assistant, user, progress, system
            if msg_type in ("assistant", "user", "progress"):
                yield message
                continue

            if msg_type == "system":
                subtype = message.get("subtype") if isinstance(message, dict) else None
                if subtype == "compact_boundary":
                    yield message
                continue

            # Yield final_response verbatim
            if msg_type == "final_response":
                yield message
                continue

            # Drop other event types (request_start, thinking, tool_use, tool_result,
            # error, max_iterations_reached, etc.)

    except Exception as exc:
        from claude_code.utils.errors import AbortError
        if isinstance(exc, AbortError):
            raise
        # Re-raise all other errors after cleanup
        raise
    finally:
        # Clean up agent-specific MCP servers
        try:
            await mcp_cleanup()
        except Exception as cleanup_exc:
            logger.debug("MCP cleanup error: %s", cleanup_exc)

        # Clean up transcript subdir mapping (stub)
        logger.debug("[Agent: %s] id=%s completed", getattr(agent_definition, "agent_type", "?"), agent_id)

    # Run built-in callback if present
    if is_built_in_agent(agent_definition):
        callback = getattr(agent_definition, "callback", None)
        if callable(callback):
            try:
                callback()
            except Exception as exc:
                logger.debug("Agent callback error: %s", exc)


# ---------------------------------------------------------------------------
# Public: filter_incomplete_tool_calls()
# ---------------------------------------------------------------------------

def filter_incomplete_tool_calls(messages: List[dict]) -> List[dict]:
    """
    Filter out assistant messages that contain tool_use blocks without
    corresponding tool_result blocks in any following user message.

    Mirrors filterIncompleteToolCalls() in runAgent.ts (line 866).

    Supports both:
    - Internal envelope format: {"type": "assistant"/"user", "message": {...}}
    - Raw API format:            {"role": "assistant"/"user", "content": [...]}

    Args:
        messages: Conversation message list.

    Returns:
        Filtered list with orphaned-tool-call assistant messages removed.
    """
    # --- collect all tool_use_ids that have a corresponding result ---
    tool_use_ids_with_results: Set[str] = set()

    for message in messages:
        msg_type = _get_message_type(message)
        msg_content = _get_message_content(message)

        if msg_type == "user" and isinstance(msg_content, list):
            for block in msg_content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and block.get("tool_use_id")
                ):
                    tool_use_ids_with_results.add(block["tool_use_id"])

    # --- drop assistant messages with orphaned tool_use blocks ---
    filtered: List[dict] = []
    for message in messages:
        msg_type = _get_message_type(message)
        msg_content = _get_message_content(message)

        if msg_type == "assistant" and isinstance(msg_content, list):
            has_incomplete = any(
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("id")
                and block["id"] not in tool_use_ids_with_results
                for block in msg_content
            )
            if has_incomplete:
                continue  # drop this message

        filtered.append(message)

    return filtered


# ---------------------------------------------------------------------------
# Public: get_agent_system_prompt()
# ---------------------------------------------------------------------------

async def get_agent_system_prompt(
    agent_definition: Any,
    tool_use_context: Any = None,
    resolved_model: str = "",
    additional_working_directories: Optional[List[str]] = None,
    resolved_tools: Optional[List[Any]] = None,
) -> List[str]:
    """
    Build the system prompt for an agent.

    Mirrors getAgentSystemPrompt() in runAgent.ts (line 908).
    Calls agent_definition.get_system_prompt() then enhances with env details.
    Falls back to DEFAULT_AGENT_PROMPT on error.
    """
    return await _get_agent_system_prompt(
        agent_definition=agent_definition,
        resolved_model=resolved_model,
        tools=resolved_tools or [],
        tool_use_context=tool_use_context,
        additional_working_directories=additional_working_directories,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _get_agent_system_prompt(
    agent_definition: Any,
    resolved_model: str = "",
    tools: Optional[List[Any]] = None,
    tool_use_context: Any = None,
    additional_working_directories: Optional[List[str]] = None,
) -> List[str]:
    """Build and enhance the agent's system prompt."""
    from claude_code.constants.prompts import (
        DEFAULT_AGENT_PROMPT,
        enhance_system_prompt_with_env_details,
    )

    tools = tools or []
    enabled_tool_names: Set[str] = set()
    for t in tools:
        name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
        if name:
            enabled_tool_names.add(name)

    # Try agent definition's get_system_prompt first
    try:
        get_sp = getattr(agent_definition, "get_system_prompt", None)
        if callable(get_sp):
            # TS version: getSystemPrompt({ toolUseContext })
            import inspect
            sig = inspect.signature(get_sp)
            if len(sig.parameters) == 0:
                raw = get_sp()
            else:
                raw = get_sp(tool_use_context=tool_use_context)
            if asyncio.iscoroutine(raw):
                raw = await raw
            agent_prompt = raw if isinstance(raw, str) else DEFAULT_AGENT_PROMPT
        else:
            agent_prompt = DEFAULT_AGENT_PROMPT
    except Exception:
        agent_prompt = DEFAULT_AGENT_PROMPT

    base_prompts = [agent_prompt]

    try:
        return await enhance_system_prompt_with_env_details(
            existing_system_prompt=base_prompts,
            model=resolved_model,
            additional_working_directories=additional_working_directories,
            enabled_tool_names=enabled_tool_names,
        )
    except Exception as exc:
        logger.debug("enhance_system_prompt_with_env_details failed: %s", exc)
        return base_prompts


async def _init_agent_mcp_servers_stub(agent_definition: Any) -> Callable:
    """
    Stub for initializeAgentMcpServers().
    The full MCP server management is not yet ported to Python.
    Returns a no-op cleanup function.
    """
    mcp_servers = getattr(agent_definition, "mcp_servers", None)
    if mcp_servers:
        logger.debug(
            "[Agent: %s] MCP server initialization not yet ported to Python "
            "(requested: %s)",
            getattr(agent_definition, "agent_type", "?"),
            mcp_servers,
        )

    async def cleanup() -> None:
        pass

    return cleanup


# ---------------------------------------------------------------------------
# Message-format helpers (shared with filter_incomplete_tool_calls)
# ---------------------------------------------------------------------------

def _get_message_type(message: dict) -> Optional[str]:
    """Return the logical message type from either message format."""
    # Internal envelope: {"type": "assistant", "message": {...}}
    if "type" in message:
        msg_type = message["type"]
        if msg_type in ("assistant", "user", "progress", "system"):
            return msg_type
    # Raw API format: {"role": "assistant"/"user", "content": [...]}
    role = message.get("role")
    if role in ("assistant", "user"):
        return role
    return None


def _get_message_content(message: dict) -> Any:
    """Return the content list from either message format."""
    # Internal envelope: message["message"]["content"]
    inner = message.get("message")
    if isinstance(inner, dict):
        return inner.get("content", [])
    # Raw API / simplified format: message["content"]
    return message.get("content", [])


def _serialize_tools(tools: Optional[List[Any]]) -> List[dict]:
    """Serialize tool objects to the API dict format."""
    if not tools:
        return []
    result = []
    for t in tools:
        if isinstance(t, dict):
            result.append(t)
            continue
        schema = (
            t.input_schema()
            if callable(getattr(t, "input_schema", None))
            else {}
        )
        result.append({
            "name": getattr(t, "name", ""),
            "description": getattr(t, "description", "") or "",
            "input_schema": schema,
        })
    return result


async def _execute_tool(
    name: str,
    input_data: dict,
    tools: Optional[List[Any]],
    context: Any,
) -> Any:
    """Find and invoke a tool by name."""
    if not tools:
        return f"Tool {name!r} not found"
    for t in tools:
        tool_name = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
        if tool_name == name:
            if isinstance(t, dict):
                return f"Tool {name!r} has no callable handler"
            call_fn = getattr(t, "call", None)
            if callable(call_fn):
                return await call_fn(input_data, context)
    return f"Tool {name!r} not found"

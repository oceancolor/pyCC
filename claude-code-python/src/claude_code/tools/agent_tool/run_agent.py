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
    Backward-compat shim — delegates to initialize_agent_mcp_servers().
    Returns only the cleanup callable (existing callers in run_agent expect this).
    """
    parent_clients: List[Any] = []
    if hasattr(agent_definition, "_parent_mcp_clients"):
        parent_clients = agent_definition._parent_mcp_clients or []
    result = await initialize_agent_mcp_servers(agent_definition, parent_clients)
    return result["cleanup"]


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


# ===========================================================================
# NEW: initialize_agent_mcp_servers() — full port of initializeAgentMcpServers()
# Mirrors runAgent.ts lines 88-238
# ===========================================================================

async def initialize_agent_mcp_servers(
    agent_definition: Any,
    parent_clients: List[Any],
) -> Dict[str, Any]:
    """
    Initialize agent-specific MCP servers defined in agent frontmatter.

    Agents can define their own MCP servers that are additive to the parent's
    MCP clients.  These servers are connected when the agent starts and cleaned
    up when the agent finishes.

    Mirrors initializeAgentMcpServers() in runAgent.ts (lines 88-238).

    Args:
        agent_definition: AgentDefinition with optional ``mcp_servers`` attribute.
        parent_clients:   MCP clients inherited from the parent context.

    Returns:
        Dict with keys:
            clients  — merged list (parent + agent-specific)
            tools    — tool descriptors from newly connected servers
            cleanup  — async callable that tears down inline-created servers
    """
    mcp_servers = getattr(agent_definition, "mcp_servers", None)
    agent_type = getattr(agent_definition, "agent_type", "?")

    # --- fast path: no agent-specific servers ---
    if not mcp_servers:
        async def _noop_cleanup() -> None:
            pass
        return {"clients": list(parent_clients), "tools": [], "cleanup": _noop_cleanup}

    # --- plugin-only policy check (mirrors isRestrictedToPluginOnly / isSourceAdminTrusted) ---
    try:
        from claude_code.utils.settings.plugin_only_policy import (
            is_restricted_to_plugin_only,
            is_source_admin_trusted,
        )
        agent_source = getattr(agent_definition, "source", None)
        agent_is_admin_trusted = is_source_admin_trusted(agent_source)
        if is_restricted_to_plugin_only("mcp") and not agent_is_admin_trusted:
            logger.debug(
                "[Agent: %s] Skipping MCP servers: strictPluginOnlyCustomization "
                "locks MCP to plugin-only (agent source: %s)",
                agent_type,
                agent_source,
            )
            async def _policy_cleanup() -> None:
                pass
            return {"clients": list(parent_clients), "tools": [], "cleanup": _policy_cleanup}
    except ImportError:
        pass  # policy module not yet ported — permissive fallback

    agent_clients: List[Any] = []
    newly_created_clients: List[Any] = []  # only inline-defined servers get cleaned up
    agent_tools: List[Any] = []

    for spec in mcp_servers:
        config = None
        name_: str
        is_newly_created = False

        if isinstance(spec, str):
            # Reference by name — look up in global MCP config registry
            name_ = spec
            try:
                from claude_code.services.mcp.config import get_mcp_config_by_name
                config = get_mcp_config_by_name(spec)
            except ImportError:
                config = None
            if config is None:
                logger.warning(
                    "[Agent: %s] MCP server not found: %s",
                    agent_type,
                    spec,
                )
                continue
        elif isinstance(spec, dict):
            # Inline definition as {"serverName": serverConfig}
            items = list(spec.items())
            if len(items) != 1:
                logger.warning(
                    "[Agent: %s] Invalid MCP server spec: expected exactly one key, got %d",
                    agent_type,
                    len(items),
                )
                continue
            server_name, server_config = items[0]
            name_ = server_name
            config = {**server_config, "scope": "dynamic"}
            is_newly_created = True
        else:
            logger.warning("[Agent: %s] Unknown MCP server spec type: %r", agent_type, spec)
            continue

        # Connect to the server
        try:
            from claude_code.services.mcp.client import connect_to_server
            client = await connect_to_server(name_, config)
        except Exception as exc:
            logger.warning("[Agent: %s] Failed to connect to MCP server %r: %s", agent_type, name_, exc)
            continue

        agent_clients.append(client)
        if is_newly_created:
            newly_created_clients.append(client)

        # Fetch tools if connected
        client_type = getattr(client, "type", None) if not isinstance(client, dict) else client.get("type")
        if client_type == "connected":
            try:
                from claude_code.services.mcp.client import fetch_tools_for_client
                fetched_tools = await fetch_tools_for_client(client)
                agent_tools.extend(fetched_tools)
                logger.debug(
                    "[Agent: %s] Connected to MCP server %r with %d tools",
                    agent_type, name_, len(fetched_tools),
                )
            except Exception as exc:
                logger.warning("[Agent: %s] fetch_tools_for_client(%r) failed: %s", agent_type, name_, exc)
        else:
            logger.warning(
                "[Agent: %s] Failed to connect to MCP server %r: type=%s",
                agent_type, name_, client_type,
            )

    # Only tear down clients that were inline-defined (not shared/referenced ones)
    captured_new = list(newly_created_clients)

    async def cleanup() -> None:
        for client in captured_new:
            ctype = getattr(client, "type", None) if not isinstance(client, dict) else client.get("type")
            if ctype == "connected":
                cleanup_fn = getattr(client, "cleanup", None)
                if callable(cleanup_fn):
                    try:
                        result = cleanup_fn()
                        if asyncio.iscoroutine(result):
                            await result
                    except Exception as exc:
                        cname = getattr(client, "name", "?")
                        logger.warning(
                            "[Agent: %s] Error cleaning up MCP server %r: %s",
                            agent_type, cname, exc,
                        )

    merged_clients = list(parent_clients) + agent_clients
    return {"clients": merged_clients, "tools": agent_tools, "cleanup": cleanup}


# ---------------------------------------------------------------------------
# Public alias: cleanup_agent_mcp_servers()
# Mirrors the cleanup() returned by initializeAgentMcpServers — here exposed
# as a standalone helper so callers can explicitly pass a client list.
# ---------------------------------------------------------------------------

async def cleanup_agent_mcp_servers(
    agent_definition: Any,
    clients: Optional[List[Any]] = None,
) -> None:
    """
    Clean up MCP server connections that were created exclusively for this agent.

    In the normal flow, cleanup is handled automatically by the closure returned
    from ``initialize_agent_mcp_servers()``.  This public function is provided
    for callers that need an explicit teardown path.

    Mirrors the cleanup() closure inside initializeAgentMcpServers() in
    runAgent.ts (lines 213-231).

    Args:
        agent_definition: The agent whose servers should be cleaned up.
        clients:          Optional explicit list of MCPServerConnection objects
                          to clean up.  When omitted, nothing is done (the
                          normal cleanup path uses the closure from
                          initialize_agent_mcp_servers).
    """
    agent_type = getattr(agent_definition, "agent_type", "?")
    if not clients:
        return
    for client in clients:
        ctype = getattr(client, "type", None) if not isinstance(client, dict) else client.get("type")
        if ctype == "connected":
            cleanup_fn = getattr(client, "cleanup", None)
            if callable(cleanup_fn):
                try:
                    result = cleanup_fn()
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as exc:
                    cname = getattr(client, "name", "?")
                    logger.warning(
                        "[Agent: %s] Error cleaning up MCP server %r: %s",
                        agent_type, cname, exc,
                    )


# ===========================================================================
# NEW: resolve_skill_name() — port of resolveSkillName() (runAgent.ts line 945)
# ===========================================================================

def resolve_skill_name(
    skill_name: str,
    all_skills: List[Any],
    agent_definition: Any,
) -> Optional[str]:
    """
    Resolve a skill name from agent frontmatter to a registered command name.

    Plugin skills are registered with namespaced names (e.g. "my-plugin:my-skill")
    but agents reference them with bare names (e.g. "my-skill").  This function
    tries three resolution strategies, mirroring resolveSkillName() in
    runAgent.ts (lines 945-973):

    1. Exact match via _has_command() (checks name, user_facing_name, aliases)
    2. Prefix with the agent's plugin name
       (e.g. "my-skill" → "my-plugin:my-skill")
    3. Suffix match — any registered skill whose name ends with ":skill_name"

    Args:
        skill_name:       The bare skill name from agent frontmatter.
        all_skills:       All registered skill/command objects.
        agent_definition: The agent that references this skill.

    Returns:
        Resolved command name string, or None if not found.
    """
    def _has_command(n: str) -> bool:
        for cmd in all_skills:
            if isinstance(cmd, dict):
                cmd_name = cmd.get("name", "")
                aliases = cmd.get("aliases", []) or []
                user_facing = cmd.get("user_facing_name", "") or ""
            else:
                cmd_name = getattr(cmd, "name", "")
                aliases = getattr(cmd, "aliases", []) or []
                user_facing = getattr(cmd, "user_facing_name", "") or ""
            if n in (cmd_name, user_facing, *aliases):
                return True
        return False

    # 1. Direct match
    if _has_command(skill_name):
        return skill_name

    # 2. Prefix with agent's plugin namespace (agentType is e.g. "pluginName:agentName")
    agent_type_str = getattr(agent_definition, "agent_type", "") or ""
    plugin_prefix = agent_type_str.split(":")[0]
    if plugin_prefix:
        qualified = f"{plugin_prefix}:{skill_name}"
        if _has_command(qualified):
            return qualified

    # 3. Suffix match — find any skill whose name ends with ":skill_name"
    suffix = f":{skill_name}"
    for cmd in all_skills:
        cmd_name = cmd.get("name", "") if isinstance(cmd, dict) else getattr(cmd, "name", "")
        if cmd_name and cmd_name.endswith(suffix):
            return cmd_name

    return None


# ===========================================================================
# NEW: Enhanced run_agent_v2() — run_agent() with full TS feature parity
# Adds: SubagentStart hooks, frontmatter hooks, skill preloading,
#       record_sidechain_transcript, write_agent_metadata, perfetto tracing,
#       plugin-only policy early exit, and full finally-block cleanup.
#
# USAGE: This is the preferred entry point for new callers.
#        Existing callers using run_agent() continue to work unchanged.
# ===========================================================================

async def run_agent_v2(
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
    Full-parity port of runAgent() from runAgent.ts.

    Adds the following features absent from the original run_agent():

    * Plugin-only policy early-exit  (isRestrictedToPluginOnly)
    * SubagentStart hooks            (executeSubagentStartHooks)
    * Frontmatter hook registration  (registerFrontmatterHooks)
    * Skill preloading from frontmatter
    * record_sidechain_transcript()  — per-message and initial batch
    * write_agent_metadata()         — agent type / worktree / description
    * Perfetto agent registration    — TODO: full tracing
    * Full finally-block cleanup     — MCP servers, session hooks, todos,
                                       shell tasks, file state cache

    Mirrors runAgent() in runAgent.ts (973 lines).
    """
    from claude_code.query import query as _query
    from claude_code.utils.uuid import create_agent_id
    from claude_code.tools.agent_tool.agent_tool_utils import resolve_agent_tools
    from claude_code.tools.agent_tool.load_agents_dir import is_built_in_agent

    override = override or {}
    agent_id: str = override.get("agent_id") or create_agent_id()
    agent_type: str = getattr(agent_definition, "agent_type", "?")

    # ------------------------------------------------------------------
    # Transcript subdir routing (e.g. workflow/<runId>/)
    # ------------------------------------------------------------------
    if transcript_subdir:
        try:
            from claude_code.utils.session_storage import set_agent_transcript_subdir
            set_agent_transcript_subdir(agent_id, transcript_subdir)
        except ImportError:
            pass

    # ------------------------------------------------------------------
    # TODO: Perfetto tracing — register agent in trace hierarchy
    # Mirrors: registerPerfettoAgent(agentId, agentType, parentId)
    # from claude_code.utils.telemetry.perfetto_tracing import (
    #     is_perfetto_tracing_enabled, register_agent as perfetto_register,
    # )
    # if is_perfetto_tracing_enabled():
    #     parent_id = getattr(tool_use_context, 'agent_id', None) or get_session_id()
    #     perfetto_register(agent_id, agent_type, parent_id)
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Plugin-only policy: early-exit for non-admin-trusted agents
    # Mirrors isRestrictedToPluginOnly check at runAgent.ts ~line 295
    # ------------------------------------------------------------------
    try:
        from claude_code.utils.settings.plugin_only_policy import (
            is_restricted_to_plugin_only,
            is_source_admin_trusted,
        )
        agent_source = getattr(agent_definition, "source", None)
        if is_restricted_to_plugin_only("agent") and not is_source_admin_trusted(agent_source):
            logger.debug(
                "[Agent: %s] Skipping: strictPluginOnlyCustomization restricts to plugin-only agents",
                agent_type,
            )
            return  # early exit — yields nothing
    except ImportError:
        pass  # policy module not yet ported

    # ------------------------------------------------------------------
    # Resolve model
    # ------------------------------------------------------------------
    resolved_model: Optional[str] = model
    if resolved_model is None:
        resolved_model = getattr(agent_definition, "model", None)
    if resolved_model is None and tool_use_context is not None:
        opts = getattr(tool_use_context, "options", {})
        resolved_model = (
            opts.get("mainLoopModel") if isinstance(opts, dict)
            else getattr(opts, "main_loop_model", None)
        )

    # ------------------------------------------------------------------
    # Context messages (fork + filter orphaned tool calls)
    # ------------------------------------------------------------------
    context_messages: List[dict] = []
    if fork_context_messages:
        context_messages = filter_incomplete_tool_calls(fork_context_messages)
    initial_messages: List[dict] = [*context_messages, *prompt_messages]

    # ------------------------------------------------------------------
    # Resolve tools
    # ------------------------------------------------------------------
    tools: List[Any] = list(available_tools or [])
    if not use_exact_tools:
        try:
            result = resolve_agent_tools(agent_definition, tools, is_async=is_async)
            tools = result.resolved_tools
        except Exception as exc:
            logger.debug("resolve_agent_tools failed: %s", exc)

    # ------------------------------------------------------------------
    # Build system prompt
    # ------------------------------------------------------------------
    if override.get("system_prompt"):
        raw = override["system_prompt"]
        system_prompt_parts: List[str] = raw if isinstance(raw, list) else [raw]
    else:
        system_prompt_parts = await _get_agent_system_prompt(
            agent_definition=agent_definition,
            resolved_model=resolved_model or "",
            tools=tools,
            tool_use_context=tool_use_context,
        )

    # ------------------------------------------------------------------
    # Abort controller / cancellation event
    # ------------------------------------------------------------------
    abort_event: Optional[asyncio.Event] = None
    if override.get("abort_controller"):
        ctrl = override["abort_controller"]
        abort_event = getattr(ctrl, "_event", None)
    if abort_event is None and tool_use_context is not None:
        abort_event = getattr(tool_use_context, "abort_event", None)
    if abort_event is None and is_async:
        abort_event = asyncio.Event()

    # ------------------------------------------------------------------
    # SubagentStart hooks — collect additional context strings
    # Mirrors executeSubagentStartHooks() at runAgent.ts ~line 534
    # ------------------------------------------------------------------
    additional_contexts: List[str] = []
    try:
        from claude_code.hooks import execute_subagent_start_hooks
        async for hook_result in execute_subagent_start_hooks(
            agent_id, agent_type, abort_event
        ):
            if isinstance(hook_result, dict):
                ctxs = hook_result.get("additional_contexts") or []
            else:
                ctxs = getattr(hook_result, "additional_contexts", None) or []
            additional_contexts.extend(ctxs)
    except (ImportError, Exception) as exc:
        logger.debug("execute_subagent_start_hooks skipped: %s", exc)

    # Inject hook context as an attachment user message
    if additional_contexts:
        try:
            from claude_code.utils.attachments import create_attachment_message
            ctx_msg = create_attachment_message({
                "type": "hook_additional_context",
                "content": additional_contexts,
                "hookName": "SubagentStart",
                "toolUseID": str(_uuid_mod.uuid4()),
                "hookEvent": "SubagentStart",
            })
            initial_messages.append(ctx_msg)
        except (ImportError, Exception) as exc:
            logger.debug("create_attachment_message failed: %s", exc)

    # ------------------------------------------------------------------
    # Register frontmatter hooks scoped to this agent's lifecycle
    # Mirrors registerFrontmatterHooks() at runAgent.ts ~line 560
    # ------------------------------------------------------------------
    _hooks_registered = False
    agent_hooks = getattr(agent_definition, "hooks", None)
    _root_set_app_state = None
    if tool_use_context is not None:
        _root_set_app_state = getattr(tool_use_context, "set_app_state_for_tasks", None)
        if _root_set_app_state is None:
            _root_set_app_state = getattr(tool_use_context, "set_app_state", None)

    if agent_hooks:
        _hooks_allowed = True
        try:
            from claude_code.utils.settings.plugin_only_policy import (
                is_restricted_to_plugin_only,
                is_source_admin_trusted,
            )
            agent_source2 = getattr(agent_definition, "source", None)
            if is_restricted_to_plugin_only("hooks") and not is_source_admin_trusted(agent_source2):
                _hooks_allowed = False
        except ImportError:
            pass

        if _hooks_allowed and _root_set_app_state is not None:
            try:
                from claude_code.utils.hooks.register_frontmatter_hooks import register_frontmatter_hooks
                register_frontmatter_hooks(
                    _root_set_app_state,
                    agent_id,
                    agent_hooks,
                    f"agent '{agent_type}'",
                    True,  # is_agent=True — converts Stop hooks to SubagentStop
                )
                _hooks_registered = True
            except (ImportError, Exception) as exc:
                logger.debug("register_frontmatter_hooks failed: %s", exc)

    # ------------------------------------------------------------------
    # Skill preloading from frontmatter (mirrors runAgent.ts ~lines 578-640)
    # ------------------------------------------------------------------
    skills_to_preload: List[str] = list(getattr(agent_definition, "skills", None) or [])
    if skills_to_preload:
        try:
            from claude_code.commands import get_skill_tool_commands
            from claude_code.bootstrap.state import get_project_root
            all_skills = await get_skill_tool_commands(get_project_root())

            for skill_name in skills_to_preload:
                resolved_sname = resolve_skill_name(skill_name, all_skills, agent_definition)
                if not resolved_sname:
                    logger.warning(
                        "[Agent: %s] Skill %r from frontmatter not found",
                        agent_type, skill_name,
                    )
                    continue

                skill = next(
                    (
                        s for s in all_skills
                        if (s.get("name") if isinstance(s, dict) else getattr(s, "name", None)) == resolved_sname
                    ),
                    None,
                )
                if skill is None:
                    continue
                skill_type = skill.get("type") if isinstance(skill, dict) else getattr(skill, "type", None)
                if skill_type != "prompt":
                    logger.warning(
                        "[Agent: %s] Skill %r is not a prompt-based skill",
                        agent_type, skill_name,
                    )
                    continue

                get_prompt_fn = (
                    skill.get("get_prompt_for_command")
                    if isinstance(skill, dict)
                    else getattr(skill, "get_prompt_for_command", None)
                )
                if callable(get_prompt_fn):
                    try:
                        content = get_prompt_fn("", tool_use_context)
                        if asyncio.iscoroutine(content):
                            content = await content
                        if content:
                            from claude_code.utils.messages import create_user_message
                            msg_content = content if isinstance(content, list) else [{"type": "text", "text": str(content)}]
                            initial_messages.append(create_user_message({"content": msg_content, "isMeta": True}))
                            logger.debug("[Agent: %s] Preloaded skill %r", agent_type, skill_name)
                    except Exception as exc:
                        logger.debug("[Agent: %s] Skill %r preload failed: %s", agent_type, skill_name, exc)
        except (ImportError, Exception) as exc:
            logger.debug("Skill preloading failed: %s", exc)

    # ------------------------------------------------------------------
    # Initialize agent-specific MCP servers
    # Mirrors runAgent.ts ~lines 643-660
    # ------------------------------------------------------------------
    parent_mcp_clients: List[Any] = []
    if tool_use_context is not None:
        opts2 = getattr(tool_use_context, "options", None)
        if opts2 is not None:
            parent_mcp_clients = (
                opts2.get("mcpClients") if isinstance(opts2, dict)
                else getattr(opts2, "mcp_clients", [])
            ) or []

    mcp_init = await initialize_agent_mcp_servers(agent_definition, parent_mcp_clients)
    merged_mcp_clients: List[Any] = mcp_init["clients"]
    agent_mcp_tools: List[Any] = mcp_init["tools"]
    mcp_cleanup_fn: Callable = mcp_init["cleanup"]

    # Merge agent MCP tools with resolved tools (dedup by name)
    if agent_mcp_tools:
        seen_names: Set[str] = set()
        merged_tools: List[Any] = []
        for t in [*tools, *agent_mcp_tools]:
            tname = t.get("name") if isinstance(t, dict) else getattr(t, "name", None)
            if tname and tname not in seen_names:
                seen_names.add(tname)
                merged_tools.append(t)
        tools = merged_tools

    # ------------------------------------------------------------------
    # Fire-and-forget: record initial messages + write agent metadata
    # Mirrors runAgent.ts ~lines 720-730
    # ------------------------------------------------------------------
    _last_recorded_uuid: Optional[str] = None
    try:
        last_msg = initial_messages[-1] if initial_messages else None
        if last_msg and isinstance(last_msg, dict):
            _last_recorded_uuid = last_msg.get("uuid") or last_msg.get("id")
    except Exception:
        pass

    async def _record_initial() -> None:
        try:
            from claude_code.utils.session_storage import record_sidechain_transcript
            await record_sidechain_transcript(initial_messages, agent_id)
        except (ImportError, Exception) as exc:
            logger.debug("record_sidechain_transcript (initial) failed: %s", exc)

    async def _write_metadata() -> None:
        try:
            from claude_code.utils.session_storage import write_agent_metadata
            metadata: Dict[str, Any] = {"agentType": agent_type}
            if worktree_path:
                metadata["worktreePath"] = worktree_path
            if description:
                metadata["description"] = description
            await write_agent_metadata(agent_id, metadata)
        except (ImportError, Exception) as exc:
            logger.debug("write_agent_metadata failed: %s", exc)

    asyncio.ensure_future(_record_initial())
    asyncio.ensure_future(_write_metadata())

    # ------------------------------------------------------------------
    # Max turns
    # ------------------------------------------------------------------
    max_agent_turns: Optional[int] = max_turns
    if max_agent_turns is None:
        max_agent_turns = getattr(agent_definition, "max_turns", None)
    if max_agent_turns is None:
        max_agent_turns = DEFAULT_MAX_AGENT_TURNS

    # ------------------------------------------------------------------
    # Inner query loop
    # ------------------------------------------------------------------
    try:
        q_params = {
            "source": query_source,
            "system_prompt": system_prompt_parts,
            "tools": tools,
            "max_turns": max_agent_turns,
            "is_non_interactive": is_async,
            "tool_use_context": tool_use_context,
        }
        if resolved_model:
            q_params["model"] = resolved_model

        async for message in _query(initial_messages, q_params, abort_event):  # type: ignore[arg-type]
            if on_query_progress is not None:
                on_query_progress()

            if not isinstance(message, dict):
                continue

            msg_type = message.get("type")

            # Forward stream_event API metrics to parent (TTFT/OTPS)
            if msg_type == "stream_event":
                event = message.get("event", {})
                if isinstance(event, dict) and event.get("type") == "message_start":
                    push_fn = getattr(tool_use_context, "push_api_metrics_entry", None)
                    if callable(push_fn) and message.get("ttftMs") is not None:
                        push_fn(message["ttftMs"])
                continue

            # Attachment messages (e.g. max_turns_reached, structured_output)
            if msg_type == "attachment":
                attachment = message.get("attachment", {})
                if isinstance(attachment, dict) and attachment.get("type") == "max_turns_reached":
                    logger.debug(
                        "[Agent: %s] Reached max turns limit (%s)",
                        agent_type, attachment.get("maxTurns"),
                    )
                    break
                yield message
                continue

            # Recordable messages: record then yield
            _is_recordable = msg_type in ("assistant", "user", "progress") or (
                msg_type == "system" and message.get("subtype") == "compact_boundary"
            )
            if _is_recordable:
                try:
                    from claude_code.utils.session_storage import record_sidechain_transcript
                    await record_sidechain_transcript([message], agent_id, _last_recorded_uuid)
                    if msg_type != "progress":
                        _last_recorded_uuid = message.get("uuid") or message.get("id")
                except (ImportError, Exception) as exc:
                    logger.debug("record_sidechain_transcript (message) failed: %s", exc)
                yield message
                continue

            if msg_type == "final_response":
                yield message
                continue

            # Drop all other event types (request_start, thinking, etc.)

        # Raise AbortError if abort signal was fired
        if abort_event is not None and abort_event.is_set():
            from claude_code.utils.errors import AbortError
            raise AbortError()

        # Run built-in agent callback
        if is_built_in_agent(agent_definition):
            callback = getattr(agent_definition, "callback", None)
            if callable(callback):
                try:
                    callback()
                except Exception as exc:
                    logger.debug("Agent callback error: %s", exc)

    finally:
        # 1. Clean up agent-specific MCP servers
        try:
            await mcp_cleanup_fn()
        except Exception as exc:
            logger.debug("MCP cleanup error: %s", exc)

        # 2. Clean up agent's session hooks
        if _hooks_registered and _root_set_app_state is not None and agent_hooks:
            try:
                from claude_code.utils.hooks.session_hooks import clear_session_hooks
                clear_session_hooks(_root_set_app_state, agent_id)
            except (ImportError, Exception) as exc:
                logger.debug("clear_session_hooks failed: %s", exc)

        # 3. Clear transcript subdir mapping
        if transcript_subdir:
            try:
                from claude_code.utils.session_storage import clear_agent_transcript_subdir
                clear_agent_transcript_subdir(agent_id)
            except (ImportError, Exception) as exc:
                logger.debug("clear_agent_transcript_subdir failed: %s", exc)

        # 4. Release agent todos entry from AppState
        if _root_set_app_state is not None:
            try:
                _aid = agent_id  # capture for closure

                def _remove_agent_todos(prev: Any) -> Any:
                    if not isinstance(prev, dict):
                        return prev
                    todos = prev.get("todos", {})
                    if _aid not in todos:
                        return prev
                    return {**prev, "todos": {k: v for k, v in todos.items() if k != _aid}}

                _root_set_app_state(_remove_agent_todos)
            except Exception as exc:
                logger.debug("Failed to remove agent todos: %s", exc)

        # 5. Kill background shell tasks spawned by this agent
        try:
            from claude_code.tasks.local_shell_task.kill_shell_tasks import kill_shell_tasks_for_agent
            get_app_state_fn = getattr(tool_use_context, "get_app_state", None)
            kill_shell_tasks_for_agent(agent_id, get_app_state_fn, _root_set_app_state)
        except (ImportError, Exception) as exc:
            logger.debug("kill_shell_tasks_for_agent failed: %s", exc)

        # 6. TODO: unregisterPerfettoAgent(agentId)
        # from claude_code.utils.telemetry.perfetto_tracing import unregister_agent
        # unregister_agent(agent_id)

        logger.debug("[Agent: %s] id=%s completed (v2)", agent_type, agent_id)

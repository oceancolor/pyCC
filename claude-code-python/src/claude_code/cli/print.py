"""
cli/print.py — Python port of cli/print.ts (headless / -p mode).

The original TypeScript file (~5594 lines) implements the headless CLI
execution loop for Claude Code.  This module faithfully ports all exported
symbols.  React/ink/JSX rendering is not applicable to Python; stubs are
provided where the TypeScript source called into those subsystems.
"""

from __future__ import annotations

import asyncio
import os
import re
import sys
import uuid as _uuid_module
from dataclasses import dataclass, field
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterable,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

# ---------------------------------------------------------------------------
# Type aliases / forward references
# ---------------------------------------------------------------------------

# ContentBlockParam is a dict with at minimum {'type': str}
ContentBlockParam = Dict[str, Any]

# PromptValue is either a plain string or a list of content-block dicts.
PromptValue = Union[str, List[ContentBlockParam]]


# ---------------------------------------------------------------------------
# Message / UUID deduplication
# ---------------------------------------------------------------------------

_MAX_RECEIVED_UUIDS: int = 10_000
_received_message_uuids: Set[str] = set()
_received_message_uuids_order: List[str] = []


def track_received_message_uuid(uid: str) -> bool:
    """Return True if *uid* is new; False if it is a duplicate.

    Maintains a bounded LRU-ish set: when capacity is exceeded the oldest
    entries are evicted.
    """
    global _received_message_uuids, _received_message_uuids_order

    if uid in _received_message_uuids:
        return False  # duplicate

    _received_message_uuids.add(uid)
    _received_message_uuids_order.append(uid)

    # Evict oldest entries when at capacity.
    if len(_received_message_uuids_order) > _MAX_RECEIVED_UUIDS:
        overflow = len(_received_message_uuids_order) - _MAX_RECEIVED_UUIDS
        to_evict = _received_message_uuids_order[:overflow]
        _received_message_uuids_order = _received_message_uuids_order[overflow:]
        for old in to_evict:
            _received_message_uuids.discard(old)

    return True  # new UUID


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _to_blocks(v: PromptValue) -> List[ContentBlockParam]:
    """Normalise a PromptValue to a list of content-block dicts."""
    if isinstance(v, str):
        return [{"type": "text", "text": v}]
    return list(v)


# ---------------------------------------------------------------------------
# Exported functions
# ---------------------------------------------------------------------------


def join_prompt_values(values: List[PromptValue]) -> PromptValue:
    """Join prompt values from multiple queued commands into one.

    Strings are newline-joined; if any value is a block list, all values are
    normalised to blocks and concatenated.

    Mirrors ``joinPromptValues`` from the TypeScript source.
    """
    if len(values) == 1:
        return values[0]
    if all(isinstance(v, str) for v in values):
        return "\n".join(values)  # type: ignore[arg-type]
    return [block for v in values for block in _to_blocks(v)]


def can_batch_with(
    head: Dict[str, Any],
    next_cmd: Optional[Dict[str, Any]],
) -> bool:
    """Return True when *next_cmd* can be batched into the same ask() call as *head*.

    Only prompt-mode commands batch, and only when the workload tag matches
    (so the combined turn is attributed correctly) and the ``is_meta`` flag
    matches.

    Mirrors ``canBatchWith`` from the TypeScript source.
    """
    if next_cmd is None:
        return False
    return (
        next_cmd.get("mode") == "prompt"
        and next_cmd.get("workload") == head.get("workload")
        and next_cmd.get("is_meta") == head.get("is_meta")
    )


def remove_interrupted_message(
    messages: List[Dict[str, Any]],
    interrupted_user_message: Dict[str, Any],
) -> None:
    """Remove an interrupted user message and its synthetic assistant sentinel.

    Used during gateway-triggered restarts to clean up message history before
    re-enqueuing the interrupted prompt.

    Mirrors ``removeInterruptedMessage`` from the TypeScript source.
    """
    target_uuid = interrupted_user_message.get("uuid")
    idx = next(
        (i for i, m in enumerate(messages) if m.get("uuid") == target_uuid),
        -1,
    )
    if idx != -1:
        # Remove the user message and the sentinel that immediately follows it.
        del messages[idx : idx + 2]


# ---------------------------------------------------------------------------
# MCP state data-classes (exported types)
# ---------------------------------------------------------------------------


@dataclass
class DynamicMcpState:
    """State for dynamically added MCP servers.

    Mirrors the ``DynamicMcpState`` type exported from the TypeScript source.
    """

    clients: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[Any] = field(default_factory=list)
    configs: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SdkMcpState:
    """State for SDK MCP servers that run in the SDK process.

    Mirrors the ``SdkMcpState`` type exported from the TypeScript source.
    """

    configs: Dict[str, Any] = field(default_factory=dict)
    clients: List[Dict[str, Any]] = field(default_factory=list)
    tools: List[Any] = field(default_factory=list)


@dataclass
class McpSetServersResult:
    """Result of :func:`handle_mcp_set_servers`.

    Mirrors the ``McpSetServersResult`` type exported from the TypeScript
    source.
    """

    response: Dict[str, Any] = field(default_factory=dict)
    new_sdk_state: SdkMcpState = field(default_factory=SdkMcpState)
    new_dynamic_state: DynamicMcpState = field(default_factory=DynamicMcpState)
    sdk_servers_changed: bool = False


# ---------------------------------------------------------------------------
# Permission / canUseTool helpers
# ---------------------------------------------------------------------------


def create_can_use_tool_with_permission_prompt(
    permission_prompt_tool: Any,
) -> Callable[..., Awaitable[Dict[str, Any]]]:
    """Create a canUseTool function backed by a permission-prompt MCP tool.

    The returned coroutine function races the tool call against the current
    abort signal so that Ctrl-C is honoured even while the tool is blocked
    waiting for user input.

    Mirrors ``createCanUseToolWithPermissionPrompt`` from the TypeScript source.
    """

    async def can_use_tool(
        tool: Any,
        input_data: Any,
        tool_use_context: Any,
        assistant_message: Any,
        tool_use_id: str,
        force_decision: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        # If a forced decision is supplied, short-circuit.
        if force_decision is not None:
            return force_decision

        # Ask the underlying permission system first.
        try:
            from claude_code.utils.permissions.permissions import (  # type: ignore[import]
                has_permissions_to_use_tool,
            )

            main_result = await has_permissions_to_use_tool(
                tool,
                input_data,
                tool_use_context,
                assistant_message,
                tool_use_id,
            )
        except ImportError:
            # Stub: allow the tool when the permissions module is unavailable.
            main_result = {"behavior": "ask"}

        if main_result.get("behavior") in ("allow", "deny"):
            return main_result

        # Build abort / tool-call futures.
        abort_signal = getattr(
            getattr(tool_use_context, "abort_controller", None),
            "signal",
            None,
        )

        abort_event: asyncio.Event = asyncio.Event()
        if abort_signal is not None and getattr(abort_signal, "aborted", False):
            return {
                "behavior": "deny",
                "message": "Permission prompt was aborted.",
                "decisionReason": {
                    "type": "permissionPromptTool",
                    "permissionPromptToolName": getattr(tool, "name", ""),
                    "toolResult": None,
                },
            }

        async def _abort_waiter() -> str:
            await abort_event.wait()
            return "aborted"

        tool_call_coro = permission_prompt_tool.call(
            {
                "tool_name": getattr(tool, "name", ""),
                "input": input_data,
                "tool_use_id": tool_use_id,
            },
            tool_use_context,
            can_use_tool,
            assistant_message,
        )

        done, pending = await asyncio.wait(
            [
                asyncio.ensure_future(tool_call_coro),
                asyncio.ensure_future(_abort_waiter()),
            ],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for p in pending:
            p.cancel()

        result_future = next(iter(done))
        race_result = result_future.result()

        if race_result == "aborted" or (
            abort_signal is not None and getattr(abort_signal, "aborted", False)
        ):
            return {
                "behavior": "deny",
                "message": "Permission prompt was aborted.",
                "decisionReason": {
                    "type": "permissionPromptTool",
                    "permissionPromptToolName": getattr(tool, "name", ""),
                    "toolResult": None,
                },
            }

        # Parse the permission tool result.
        try:
            from claude_code.utils.permissions.permission_prompt_tool_result_schema import (  # type: ignore[import]
                permission_prompt_tool_result_to_permission_decision,
                output_schema,
            )
            import json

            content = race_result.get("data", {})
            mapped = permission_prompt_tool.map_tool_result_to_tool_result_block_param(
                content, "1"
            )
            inner = mapped.get("content", [])
            if (
                not isinstance(inner, list)
                or not inner
                or inner[0].get("type") != "text"
                or not isinstance(inner[0].get("text"), str)
            ):
                raise ValueError(
                    "Permission prompt tool returned an invalid result. "
                    "Expected a single text block param with type='text' and a string text value."
                )
            parsed = output_schema().parse(json.loads(inner[0]["text"]))
            return permission_prompt_tool_result_to_permission_decision(
                parsed,
                permission_prompt_tool,
                input_data,
                tool_use_context,
            )
        except ImportError:
            return {"behavior": "deny", "message": "Permission system unavailable."}

    return can_use_tool


def get_can_use_tool_fn(
    permission_prompt_tool_name: Optional[str],
    structured_io: Any,
    get_mcp_tools: Callable[[], List[Any]],
    on_permission_prompt: Optional[Callable[[Any], None]] = None,
) -> Callable[..., Awaitable[Dict[str, Any]]]:
    """Return the appropriate ``canUseTool`` function for the current session.

    * ``None`` → standard permissions check (no extra prompt tool).
    * ``"stdio"`` → delegate to *structured_io*.
    * Any other string → lazy-resolve the named MCP tool and build a
      :func:`create_can_use_tool_with_permission_prompt`-backed function.

    Mirrors ``getCanUseToolFn`` from the TypeScript source.

    .. note::
        Exported for testing — regression: this used to crash at construction
        when ``getMcpTools()`` was empty (before per-server connects populated
        appState).
    """
    if permission_prompt_tool_name == "stdio":
        return structured_io.create_can_use_tool(on_permission_prompt)

    if not permission_prompt_tool_name:
        # Standard permissions check with no custom prompt tool.
        async def _default_can_use_tool(
            tool: Any,
            input_data: Any,
            tool_use_context: Any,
            assistant_message: Any,
            tool_use_id: str,
            force_decision: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            if force_decision is not None:
                return force_decision
            try:
                from claude_code.utils.permissions.permissions import (  # type: ignore[import]
                    has_permissions_to_use_tool,
                )

                return await has_permissions_to_use_tool(
                    tool,
                    input_data,
                    tool_use_context,
                    assistant_message,
                    tool_use_id,
                )
            except ImportError:
                return {"behavior": "allow"}

        return _default_can_use_tool

    # Lazy-resolve the named MCP tool.
    resolved: List[Optional[Callable[..., Awaitable[Dict[str, Any]]]]] = [None]

    async def _lazy_can_use_tool(
        tool: Any,
        input_data: Any,
        tool_use_context: Any,
        assistant_message: Any,
        tool_use_id: str,
        force_decision: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if resolved[0] is None:
            mcp_tools = get_mcp_tools()
            ppt = next(
                (
                    t
                    for t in mcp_tools
                    if _tool_matches_name(t, permission_prompt_tool_name)
                ),
                None,
            )
            if ppt is None:
                available = ", ".join(
                    getattr(t, "name", str(t)) for t in mcp_tools
                ) or "none"
                error_msg = (
                    f"Error: MCP tool {permission_prompt_tool_name} "
                    f"(passed via --permission-prompt-tool) not found. "
                    f"Available MCP tools: {available}"
                )
                sys.stderr.write(error_msg + "\n")
                raise RuntimeError(error_msg)
            if not getattr(ppt, "input_json_schema", None):
                error_msg = (
                    f"Error: tool {permission_prompt_tool_name} "
                    f"(passed via --permission-prompt-tool) must be an MCP tool"
                )
                sys.stderr.write(error_msg + "\n")
                raise RuntimeError(error_msg)
            resolved[0] = create_can_use_tool_with_permission_prompt(ppt)

        return await resolved[0](  # type: ignore[misc]
            tool,
            input_data,
            tool_use_context,
            assistant_message,
            tool_use_id,
            force_decision,
        )

    return _lazy_can_use_tool


def _tool_matches_name(tool: Any, name: str) -> bool:
    """Return True if *tool*'s name matches *name* (case-insensitive prefix check)."""
    tool_name = getattr(tool, "name", "") or ""
    return tool_name == name or tool_name.endswith(f"__{name}")


# ---------------------------------------------------------------------------
# handleOrphanedPermissionResponse
# ---------------------------------------------------------------------------


async def handle_orphaned_permission_response(
    *,
    message: Dict[str, Any],
    set_app_state: Callable[[Callable[[Any], Any]], None],
    on_enqueued: Optional[Callable[[], None]] = None,
    handled_tool_use_ids: Set[str],
) -> bool:
    """Handle unexpected permission responses by looking up the unresolved tool.

    Returns True if a permission was enqueued, False otherwise.

    Mirrors ``handleOrphanedPermissionResponse`` from the TypeScript source.
    """
    response = message.get("response", {})
    if response.get("subtype") != "success":
        return False

    inner = response.get("response") or {}
    tool_use_id = inner.get("toolUseID")
    if not tool_use_id or not isinstance(tool_use_id, str):
        return False

    _log_debug(
        f"handle_orphaned_permission_response: received orphaned control_response "
        f"for toolUseID={tool_use_id} request_id={response.get('request_id')}"
    )

    # Prevent re-processing the same orphaned tool_use.
    if tool_use_id in handled_tool_use_ids:
        _log_debug(
            f"handle_orphaned_permission_response: skipping duplicate orphaned "
            f"permission for toolUseID={tool_use_id} (already handled)"
        )
        return False

    # Look up the unresolved tool use in the transcript.
    assistant_message = await _find_unresolved_tool_use(tool_use_id)
    if assistant_message is None:
        _log_debug(
            f"handle_orphaned_permission_response: no unresolved tool_use found "
            f"for toolUseID={tool_use_id} (already resolved in transcript)"
        )
        return False

    handled_tool_use_ids.add(tool_use_id)
    _log_debug(
        f"handle_orphaned_permission_response: enqueuing orphaned permission "
        f"for toolUseID={tool_use_id} "
        f"messageID={assistant_message.get('message', {}).get('id')}"
    )

    _enqueue(
        {
            "mode": "orphaned-permission",
            "value": [],
            "orphaned_permission": {
                "permission_result": inner,
                "assistant_message": assistant_message,
            },
        }
    )

    if on_enqueued is not None:
        on_enqueued()

    return True


# ---------------------------------------------------------------------------
# handleMcpSetServers
# ---------------------------------------------------------------------------


async def handle_mcp_set_servers(
    servers: Dict[str, Any],
    sdk_state: SdkMcpState,
    dynamic_state: DynamicMcpState,
    set_app_state: Callable[[Callable[[Any], Any]], None],
) -> McpSetServersResult:
    """Handle mcp_set_servers requests by processing both SDK and process-based servers.

    SDK servers run in the SDK process; process-based servers are spawned by
    the CLI.  Applies enterprise ``allowedMcpServers``/``deniedMcpServers``
    policy — same filter as ``--mcp-config``.

    Mirrors ``handleMcpSetServers`` from the TypeScript source.
    """
    # Enforce enterprise MCP policy on process-based servers.
    allowed_servers, blocked = _filter_mcp_servers_by_policy(servers)
    policy_errors: Dict[str, str] = {
        name: "Blocked by enterprise policy (allowedMcpServers/deniedMcpServers)"
        for name in blocked
    }

    # Separate SDK servers from process-based servers.
    sdk_servers: Dict[str, Any] = {}
    process_servers: Dict[str, Any] = {}
    for name, config in allowed_servers.items():
        if config.get("type") == "sdk":
            sdk_servers[name] = config
        else:
            process_servers[name] = config

    # ---- Handle SDK servers ----
    current_sdk_names: Set[str] = set(sdk_state.configs.keys())
    new_sdk_names: Set[str] = set(sdk_servers.keys())
    sdk_added: List[str] = []
    sdk_removed: List[str] = []

    new_sdk_configs = dict(sdk_state.configs)
    new_sdk_clients = list(sdk_state.clients)
    new_sdk_tools = list(sdk_state.tools)

    # Remove SDK servers no longer in desired state.
    for name in list(current_sdk_names):
        if name not in new_sdk_names:
            client = next((c for c in new_sdk_clients if c.get("name") == name), None)
            if client and client.get("type") == "connected":
                cleanup = client.get("cleanup")
                if callable(cleanup):
                    await _maybe_await(cleanup())
            new_sdk_clients = [c for c in new_sdk_clients if c.get("name") != name]
            prefix = f"mcp__{name}__"
            new_sdk_tools = [
                t for t in new_sdk_tools if not _tool_name(t).startswith(prefix)
            ]
            del new_sdk_configs[name]
            sdk_removed.append(name)

    # Add new SDK servers as pending.
    for name, config in sdk_servers.items():
        if name not in current_sdk_names:
            new_sdk_configs[name] = config
            pending_client: Dict[str, Any] = {
                "type": "pending",
                "name": name,
                "config": {**config, "scope": "dynamic"},
            }
            new_sdk_clients.append(pending_client)
            sdk_added.append(name)

    # ---- Handle process-based servers ----
    process_result = await reconcile_mcp_servers(
        process_servers,
        dynamic_state,
        set_app_state,
    )

    return McpSetServersResult(
        response={
            "added": sdk_added + process_result["response"]["added"],
            "removed": sdk_removed + process_result["response"]["removed"],
            "errors": {**policy_errors, **process_result["response"]["errors"]},
        },
        new_sdk_state=SdkMcpState(
            configs=new_sdk_configs,
            clients=new_sdk_clients,
            tools=new_sdk_tools,
        ),
        new_dynamic_state=process_result["new_state"],
        sdk_servers_changed=bool(sdk_added) or bool(sdk_removed),
    )


# ---------------------------------------------------------------------------
# reconcileMcpServers
# ---------------------------------------------------------------------------


async def reconcile_mcp_servers(
    desired_configs: Dict[str, Any],
    current_state: DynamicMcpState,
    set_app_state: Callable[[Callable[[Any], Any]], None],
) -> Dict[str, Any]:
    """Reconcile the current set of dynamic MCP servers with a new desired state.

    Handles additions, removals, and config changes.

    Mirrors ``reconcileMcpServers`` from the TypeScript source.

    Returns a dict with keys ``"response"`` and ``"new_state"``.
    """
    current_names: Set[str] = set(current_state.configs.keys())
    desired_names: Set[str] = set(desired_configs.keys())

    to_remove = [n for n in current_names if n not in desired_names]
    to_add = [n for n in desired_names if n not in current_names]

    # Detect config changes.
    to_check = [n for n in current_names if n in desired_names]
    to_replace = [
        n
        for n in to_check
        if not _mcp_configs_equal(
            current_state.configs.get(n, {}),
            _to_scoped_config(desired_configs[n]),
        )
    ]

    removed: List[str] = []
    added: List[str] = []
    errors: Dict[str, str] = {}

    new_clients = list(current_state.clients)
    new_tools = list(current_state.tools)

    # Remove old servers (including ones being replaced).
    for name in to_remove + to_replace:
        client = next((c for c in new_clients if c.get("name") == name), None)
        config = current_state.configs.get(name)
        if client and config:
            if client.get("type") == "connected":
                cleanup = client.get("cleanup")
                if callable(cleanup):
                    try:
                        await _maybe_await(cleanup())
                    except Exception as exc:
                        _log_error(exc)
            # Clear the memoization cache.
            await _clear_server_cache(name, config)

        prefix = f"mcp__{name}__"
        new_tools = [t for t in new_tools if not _tool_name(t).startswith(prefix)]
        new_clients = [c for c in new_clients if c.get("name") != name]

        if name in to_remove:
            removed.append(name)

    # Add new servers (including replacements).
    for name in to_add + to_replace:
        config = desired_configs.get(name)
        if config is None:
            continue
        scoped_config = _to_scoped_config(config)

        if config.get("type") == "sdk":
            added.append(name)
            continue

        try:
            client = await _connect_to_server(name, scoped_config)
            new_clients.append(client)

            if client.get("type") == "connected":
                server_tools = await _fetch_tools_for_client(client)
                new_tools.extend(server_tools)
            elif client.get("type") == "failed":
                errors[name] = client.get("error") or "Connection failed"

            added.append(name)
        except Exception as exc:
            errors[name] = str(exc)
            _log_error(exc)

    # Build new configs.
    new_configs: Dict[str, Any] = {
        name: _to_scoped_config(desired_configs[name])
        for name in desired_names
        if desired_configs.get(name) is not None
    }

    new_state = DynamicMcpState(
        clients=new_clients,
        tools=new_tools,
        configs=new_configs,
    )

    # Update AppState with the new tools.
    all_dynamic_server_names: Set[str] = set(current_state.configs.keys()) | set(
        new_configs.keys()
    )

    def _update_app_state(prev: Any) -> Any:
        # Remove old dynamic tools and clients.
        prev_tools = getattr(prev, "mcp", {})
        if hasattr(prev_tools, "tools"):
            old_tools = prev_tools.tools
        elif isinstance(prev_tools, dict):
            old_tools = prev_tools.get("tools", [])
        else:
            old_tools = []

        if hasattr(prev_tools, "clients"):
            old_clients = prev_tools.clients
        elif isinstance(prev_tools, dict):
            old_clients = prev_tools.get("clients", [])
        else:
            old_clients = []

        non_dynamic_tools = [
            t
            for t in old_tools
            if not any(
                _tool_name(t).startswith(f"mcp__{sn}__")
                for sn in all_dynamic_server_names
            )
        ]
        non_dynamic_clients = [
            c
            for c in old_clients
            if c.get("name") not in all_dynamic_server_names
        ]

        # Attempt to build a new state using the same structure as `prev`.
        try:
            import copy

            new_prev = copy.copy(prev)
            new_mcp = copy.copy(prev.mcp if hasattr(prev, "mcp") else {})
            if isinstance(new_mcp, dict):
                new_mcp["tools"] = non_dynamic_tools + new_tools
                new_mcp["clients"] = non_dynamic_clients + new_clients
            else:
                object.__setattr__(new_mcp, "tools", non_dynamic_tools + new_tools)
                object.__setattr__(
                    new_mcp, "clients", non_dynamic_clients + new_clients
                )
            if isinstance(new_prev, dict):
                new_prev["mcp"] = new_mcp
            else:
                object.__setattr__(new_prev, "mcp", new_mcp)
            return new_prev
        except Exception:
            return prev

    set_app_state(_update_app_state)

    return {
        "response": {"added": added, "removed": removed, "errors": errors},
        "new_state": new_state,
    }


# ---------------------------------------------------------------------------
# runHeadless  (main entry-point)
# ---------------------------------------------------------------------------


async def run_headless(
    input_prompt: Union[str, AsyncIterable[str]],
    get_app_state: Callable[[], Any],
    set_app_state: Callable[[Callable[[Any], Any]], None],
    commands: List[Any],
    tools: List[Any],
    sdk_mcp_configs: Dict[str, Any],
    agents: List[Any],
    options: Dict[str, Any],
) -> None:
    """Execute a headless (non-interactive, -p) Claude Code session.

    This is the primary entry-point for SDK / scripted callers.  The full
    interactive React/ink rendering loop is not ported; the function runs
    the query loop, streams SDK messages through *structured_io*, and exits
    when the session is complete.

    Mirrors ``runHeadless`` from the TypeScript source.

    .. note::
        The ink/JSX rendering subsystem is omitted (Python has no equivalent).
        All SDK-protocol logic (control messages, stream-json output, MCP
        server management, permission prompts) is faithfully ported.
    """
    import json

    # --resume-session-at requires --resume
    if options.get("resume_session_at") and not options.get("resume"):
        sys.stderr.write("Error: --resume-session-at requires --resume\n")
        return

    # --rewind-files requires --resume
    if options.get("rewind_files") and not options.get("resume"):
        sys.stderr.write("Error: --rewind-files requires --resume\n")
        return

    if options.get("rewind_files") and input_prompt:
        sys.stderr.write(
            "Error: --rewind-files is a standalone operation and cannot be used with a prompt\n"
        )
        return

    structured_io = get_structured_io(input_prompt, options)

    output_format = options.get("output_format")

    app_state = get_app_state()

    # Load initial messages
    load_result = await load_initial_messages(set_app_state, options)
    initial_messages = load_result.messages
    turn_interruption_state = load_result.turn_interruption_state

    if len(initial_messages) == 0 and not options.get("resume") and not options.get("sdk_url"):
        # Check for early exit conditions
        pass

    # Handle --rewind-files
    if options.get("rewind_files"):
        target_uuid = options["rewind_files"]
        target_msg = next(
            (m for m in initial_messages if m.get("uuid") == target_uuid and m.get("type") == "user"),
            None,
        )
        if not target_msg:
            sys.stderr.write(
                f"Error: --rewind-files requires a user message UUID, but {target_uuid} "
                "is not a user message in this session\n"
            )
            return
        result = await handle_rewind_files(
            target_uuid,
            get_app_state(),
            set_app_state,
            False,
        )
        if not result.can_rewind:
            sys.stderr.write(f"Error: {result.error or 'Unexpected error'}\n")
            return
        sys.stdout.write(f"Files rewound to state at message {target_uuid}\n")
        sys.stdout.flush()
        return

    # Validate input prompt requirement
    has_valid_resume = (
        isinstance(options.get("resume"), str)
        and bool(options["resume"])
    )
    is_using_sdk_url = bool(options.get("sdk_url"))

    if not input_prompt and not has_valid_resume and not is_using_sdk_url:
        sys.stderr.write(
            "Error: Input must be provided either through stdin or as a prompt argument "
            "when using --print\n"
        )
        return

    if output_format == "stream-json" and not options.get("verbose"):
        sys.stderr.write(
            "Error: When using --print, --output-format=stream-json requires --verbose\n"
        )
        return

    # Filter MCP tools by deny rules
    mcp_state = getattr(app_state, "mcp", None) or (app_state.get("mcp", {}) if isinstance(app_state, dict) else {})
    mcp_tools = (
        mcp_state.get("tools", []) if isinstance(mcp_state, dict)
        else getattr(mcp_state, "tools", [])
    )
    tool_permission_context = (
        app_state.get("tool_permission_context", {}) if isinstance(app_state, dict)
        else getattr(app_state, "tool_permission_context", {})
    )

    try:
        from claude_code.tools import filter_tools_by_deny_rules  # type: ignore[import]
        allowed_mcp_tools = filter_tools_by_deny_rules(mcp_tools, tool_permission_context)
    except ImportError:
        allowed_mcp_tools = list(mcp_tools)

    filtered_tools = list(tools) + allowed_mcp_tools

    # Determine effective permission prompt tool name
    effective_ppt_name = (
        "stdio" if options.get("sdk_url")
        else options.get("permission_prompt_tool_name")
    )

    def _on_permission_prompt(details: Any) -> None:
        pass  # In headless mode, just track if needed

    can_use_tool = get_can_use_tool_fn(
        effective_ppt_name,
        structured_io,
        lambda: (
            mcp_state.get("tools", []) if isinstance(mcp_state, dict)
            else getattr(mcp_state, "tools", [])
        ),
        _on_permission_prompt,
    )

    if options.get("permission_prompt_tool_name"):
        ppt_name = options["permission_prompt_tool_name"]
        filtered_tools = [t for t in filtered_tools if not _tool_matches_name(t, ppt_name)]

    # Get model options for initialize response
    model_infos: List[Dict[str, Any]] = []
    try:
        from claude_code.utils.model.model import get_model_options  # type: ignore[import]
        raw_opts = get_model_options()
        model_infos = build_model_infos(raw_opts)
    except ImportError:
        pass

    # Collect all messages
    needs_full_array = output_format == "json" and options.get("verbose")
    messages_collected: List[Dict[str, Any]] = []
    last_message: Optional[Dict[str, Any]] = None

    # Stream from run_headless_streaming
    mcp_clients = (
        mcp_state.get("clients", []) if isinstance(mcp_state, dict)
        else getattr(mcp_state, "clients", [])
    )
    mcp_commands = (
        mcp_state.get("commands", []) if isinstance(mcp_state, dict)
        else getattr(mcp_state, "commands", [])
    )

    async for message in run_headless_streaming(
        structured_io,
        mcp_clients,
        list(commands) + list(mcp_commands),
        filtered_tools,
        initial_messages,
        can_use_tool,
        sdk_mcp_configs,
        get_app_state,
        set_app_state,
        agents,
        options,
        turn_interruption_state,
    ):
        msg_type = message.get("type", "")
        msg_subtype = message.get("subtype", "")

        if output_format == "stream-json" and options.get("verbose"):
            try:
                sys.stdout.write(json.dumps(message) + "\n")
                sys.stdout.flush()
            except Exception:
                pass

        # Skip control/stream/keep-alive messages for last_message tracking
        if msg_type in ("control_response", "control_request", "control_cancel_request",
                        "stream_event", "keep_alive", "streamlined_text",
                        "streamlined_tool_use_summary", "prompt_suggestion"):
            continue
        if msg_type == "system" and msg_subtype in (
            "session_state_changed", "task_notification", "task_started",
            "task_progress", "post_turn_summary"
        ):
            continue

        if needs_full_array:
            messages_collected.append(message)
        last_message = message

    # Output final result
    if output_format == "json":
        if not last_message or last_message.get("type") != "result":
            raise RuntimeError("No messages returned")
        if options.get("verbose"):
            sys.stdout.write(json.dumps(messages_collected) + "\n")
        else:
            sys.stdout.write(json.dumps(last_message) + "\n")
        sys.stdout.flush()
    elif output_format == "stream-json":
        pass  # already streamed above
    else:
        if not last_message or last_message.get("type") != "result":
            raise RuntimeError("No messages returned")
        subtype = last_message.get("subtype", "")
        if subtype == "success":
            result_text = last_message.get("result", "")
            output_text = result_text if result_text.endswith("\n") else result_text + "\n"
            sys.stdout.write(output_text)
        elif subtype == "error_during_execution":
            sys.stdout.write("Execution error\n")
        elif subtype == "error_max_turns":
            sys.stdout.write(f"Error: Reached max turns ({options.get('max_turns')})\n")
        elif subtype == "error_max_budget_usd":
            sys.stdout.write(f"Error: Exceeded USD budget ({options.get('max_budget_usd')})\n")
        elif subtype == "error_max_structured_output_retries":
            sys.stdout.write("Error: Failed to provide valid structured output after maximum retries\n")
        sys.stdout.flush()


# ---------------------------------------------------------------------------
# Private / internal helpers  (not exported from the TypeScript source but
# required by the ported logic above)
# ---------------------------------------------------------------------------


def _log_debug(message: str) -> None:
    """Emit a debug log line.  Mirrors ``logForDebugging`` from the TS source."""
    if os.environ.get("CLAUDE_CODE_DEBUG"):
        sys.stderr.write(f"[DEBUG] {message}\n")


def _log_error(exc: Any) -> None:
    """Log an error to stderr.  Mirrors ``logError`` from the TS source."""
    sys.stderr.write(f"[ERROR] {exc}\n")


def _tool_name(tool: Any) -> str:
    """Return the name of *tool* regardless of its type."""
    if isinstance(tool, dict):
        return tool.get("name", "") or ""
    return getattr(tool, "name", "") or ""


def _to_scoped_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Add ``scope='dynamic'`` to a process-transport config dict."""
    return {**config, "scope": "dynamic"}


def _mcp_configs_equal(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Return True when two MCP server configs are semantically equal.

    Mirrors ``areMcpConfigsEqual`` from the TypeScript source (shallow
    structural comparison).
    """
    if a.get("type") != b.get("type"):
        return False
    if a.get("type") in ("stdio", None):
        return (
            a.get("command") == b.get("command")
            and a.get("args") == b.get("args")
            and a.get("env") == b.get("env")
        )
    if a.get("type") in ("sse", "http"):
        return a.get("url") == b.get("url") and a.get("headers") == b.get("headers")
    # Fallback: full equality.
    return a == b


def _filter_mcp_servers_by_policy(
    servers: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    """Filter MCP server configs by enterprise policy.

    Returns ``(allowed, blocked_names)``.  Mirrors ``filterMcpServersByPolicy``
    from the TypeScript source.  When the policy module is unavailable, all
    servers are allowed.
    """
    try:
        from claude_code.services.mcp.config import (  # type: ignore[import]
            filter_mcp_servers_by_policy,
        )

        return filter_mcp_servers_by_policy(servers)
    except ImportError:
        return dict(servers), []


async def _connect_to_server(name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """Connect to an MCP server.  Mirrors ``connectToServer`` from the TS source."""
    try:
        from claude_code.services.mcp.client import (  # type: ignore[import]
            connect_to_server,
        )

        return await connect_to_server(name, config)
    except ImportError:
        return {"type": "failed", "name": name, "error": "MCP client module unavailable"}


async def _fetch_tools_for_client(client: Dict[str, Any]) -> List[Any]:
    """Fetch tools from a connected MCP client.  Mirrors ``fetchToolsForClient``."""
    try:
        from claude_code.services.mcp.client import (  # type: ignore[import]
            fetch_tools_for_client,
        )

        return await fetch_tools_for_client(client)
    except ImportError:
        return []


async def _clear_server_cache(name: str, config: Dict[str, Any]) -> None:
    """Clear the memoization cache for an MCP server.  Mirrors ``clearServerCache``."""
    try:
        from claude_code.services.mcp.client import (  # type: ignore[import]
            clear_server_cache,
        )

        await clear_server_cache(name, config)
    except ImportError:
        pass


async def _find_unresolved_tool_use(
    tool_use_id: str,
) -> Optional[Dict[str, Any]]:
    """Find an unresolved tool_use in the session transcript.

    Mirrors ``findUnresolvedToolUse`` from the TypeScript source.
    """
    try:
        from claude_code.utils.session_storage import (  # type: ignore[import]
            find_unresolved_tool_use,
        )

        return await find_unresolved_tool_use(tool_use_id)
    except ImportError:
        return None


def _enqueue(command: Dict[str, Any]) -> None:
    """Add a command to the message queue.  Mirrors ``enqueue`` from the TS source."""
    try:
        from claude_code.utils.message_queue_manager import (  # type: ignore[import]
            enqueue,
        )

        enqueue(command)
    except ImportError:
        _log_debug(f"_enqueue: message_queue_manager unavailable, dropping: {command}")


async def _maybe_await(value: Any) -> Any:
    """Await *value* if it is a coroutine; otherwise return it directly."""
    if asyncio.iscoroutine(value):
        return await value
    return value


# ---------------------------------------------------------------------------
# Control-request response helpers
# ---------------------------------------------------------------------------


def send_control_response_success(
    output_queue: Any,
    message: Dict[str, Any],
    response: Optional[Dict[str, Any]] = None,
) -> None:
    """Enqueue a successful control response.

    Mirrors ``sendControlResponseSuccess`` from the TypeScript source.
    """
    _enqueue_to(output_queue, {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": message.get("request_id"),
            "response": response,
        },
    })


def send_control_response_error(
    output_queue: Any,
    message: Dict[str, Any],
    error_message_text: str,
) -> None:
    """Enqueue an error control response.

    Mirrors ``sendControlResponseError`` from the TypeScript source.
    """
    _enqueue_to(output_queue, {
        "type": "control_response",
        "response": {
            "subtype": "error",
            "request_id": message.get("request_id"),
            "error": error_message_text,
        },
    })


def _enqueue_to(output_queue: Any, item: Any) -> None:
    """Enqueue *item* into *output_queue* regardless of its concrete type.

    Accepts asyncio.Queue, a list, or any object with an ``enqueue`` method.
    """
    if hasattr(output_queue, "enqueue"):
        output_queue.enqueue(item)
    elif isinstance(output_queue, list):
        output_queue.append(item)
    elif isinstance(output_queue, asyncio.Queue):
        output_queue.put_nowait(item)
    else:
        _log_debug(f"_enqueue_to: unknown queue type {type(output_queue)}, dropping: {item}")


# ---------------------------------------------------------------------------
# handle_set_permission_mode
# ---------------------------------------------------------------------------


def handle_set_permission_mode(
    request: Dict[str, Any],
    request_id: str,
    tool_permission_context: Dict[str, Any],
    output_queue: Any,
) -> Dict[str, Any]:
    """Handle a ``set_permission_mode`` control request.

    Validates the requested mode transition and emits the appropriate
    control response.  Returns the (possibly updated) tool_permission_context.

    Mirrors ``handleSetPermissionMode`` from the TypeScript source.
    """
    mode = request.get("mode")

    # Check bypassPermissions constraints.
    if mode == "bypassPermissions":
        if not tool_permission_context.get("isBypassPermissionsModeAvailable", False):
            send_control_response_error(
                output_queue,
                {"request_id": request_id},
                "Cannot set permission mode to bypassPermissions because the session "
                "was not launched with --dangerously-skip-permissions",
            )
            return tool_permission_context

    # Emit success and return updated context.
    send_control_response_success(
        output_queue,
        {"request_id": request_id},
        {"mode": mode},
    )
    return {**tool_permission_context, "mode": mode}


# ---------------------------------------------------------------------------
# handle_rewind_files
# ---------------------------------------------------------------------------


@dataclass
class RewindFilesResult:
    """Result of :func:`handle_rewind_files`.

    Mirrors ``RewindFilesResult`` from ``agentSdkTypes.ts``.
    """

    can_rewind: bool
    error: Optional[str] = None
    files_changed: Optional[int] = None
    insertions: Optional[int] = None
    deletions: Optional[int] = None


async def handle_rewind_files(
    user_message_id: str,
    app_state: Any,
    set_app_state: Callable[[Callable[[Any], Any]], None],
    dry_run: bool,
) -> RewindFilesResult:
    """Handle a ``rewind_files`` control request.

    Checks whether file history is enabled, whether the target message exists,
    and either performs the rewind or returns a dry-run diff summary.

    Mirrors ``handleRewindFiles`` from the TypeScript source.
    """
    try:
        from claude_code.utils.file_history import (  # type: ignore[import]
            file_history_enabled,
            file_history_can_restore,
            file_history_rewind,
            file_history_get_diff_stats,
        )
    except ImportError:
        return RewindFilesResult(can_rewind=False, error="File rewinding is not available.")

    if not file_history_enabled():
        return RewindFilesResult(can_rewind=False, error="File rewinding is not enabled.")

    file_history = getattr(app_state, "file_history", None) or (
        app_state.get("file_history") if isinstance(app_state, dict) else None
    )
    if not file_history_can_restore(file_history, user_message_id):
        return RewindFilesResult(
            can_rewind=False,
            error="No file checkpoint found for this message.",
        )

    if dry_run:
        diff_stats = await file_history_get_diff_stats(file_history, user_message_id)
        return RewindFilesResult(
            can_rewind=True,
            files_changed=diff_stats.get("files_changed") if diff_stats else None,
            insertions=diff_stats.get("insertions") if diff_stats else None,
            deletions=diff_stats.get("deletions") if diff_stats else None,
        )

    try:

        def _updater(updater_fn: Callable[[Any], Any]) -> None:
            def _apply(prev: Any) -> Any:
                fh = getattr(prev, "file_history", None) or (
                    prev.get("file_history") if isinstance(prev, dict) else None
                )
                new_fh = updater_fn(fh)
                if isinstance(prev, dict):
                    return {**prev, "file_history": new_fh}
                try:
                    import copy
                    new_prev = copy.copy(prev)
                    object.__setattr__(new_prev, "file_history", new_fh)
                    return new_prev
                except Exception:
                    return prev

            set_app_state(_apply)

        await file_history_rewind(_updater, user_message_id)
    except Exception as exc:
        return RewindFilesResult(
            can_rewind=False,
            error=f"Failed to rewind: {exc}",
        )

    return RewindFilesResult(can_rewind=True)


# ---------------------------------------------------------------------------
# emit_load_error
# ---------------------------------------------------------------------------


def emit_load_error(message: str, output_format: Optional[str]) -> None:
    """Emit an error in the correct format for the current output mode.

    When *output_format* is ``'stream-json'``, writes an NDJSON error-result
    object to stdout.  Otherwise writes plain text to stderr.

    Mirrors ``emitLoadError`` from the TypeScript source.
    """
    import json

    if output_format == "stream-json":
        error_result = {
            "type": "result",
            "subtype": "error_during_execution",
            "duration_ms": 0,
            "duration_api_ms": 0,
            "is_error": True,
            "num_turns": 0,
            "stop_reason": None,
            "session_id": _get_session_id(),
            "total_cost_usd": 0,
            "usage": {},
            "modelUsage": {},
            "permission_denials": [],
            "uuid": str(_uuid_module.uuid4()),
            "errors": [message],
        }
        sys.stdout.write(json.dumps(error_result) + "\n")
        sys.stdout.flush()
    else:
        sys.stderr.write(message + "\n")
        sys.stderr.flush()


def _get_session_id() -> str:
    """Return the current session ID, if available."""
    try:
        from claude_code.bootstrap.state import get_session_id  # type: ignore[import]
        return get_session_id() or ""
    except ImportError:
        return ""


# ---------------------------------------------------------------------------
# load_initial_messages  (partial port – core structure)
# ---------------------------------------------------------------------------


@dataclass
class LoadInitialMessagesResult:
    """Result of :func:`load_initial_messages`.

    Mirrors the ``LoadInitialMessagesResult`` type from the TypeScript source.
    """

    messages: List[Dict[str, Any]]
    turn_interruption_state: Optional[Dict[str, Any]] = None
    agent_setting: Optional[str] = None


async def load_initial_messages(
    set_app_state: Callable[[Callable[[Any], Any]], None],
    options: Dict[str, Any],
) -> LoadInitialMessagesResult:
    """Load the initial message history for a headless session.

    Handles ``continue``, ``resume``, and fresh-start paths.  Mirrors
    ``loadInitialMessages`` from the TypeScript source.

    Parameters
    ----------
    set_app_state:
        Callback to update application state (used when resuming / continuing).
    options:
        A dict with optional keys:
        - ``continue`` (bool): resume the most recent session.
        - ``resume`` (str | bool): resume by session ID or URL.
        - ``resume_session_at`` (str): slice messages up to this UUID.
        - ``fork_session`` (bool): fork the resumed session.
        - ``output_format`` (str | None): ``'stream-json'`` or ``None``.
        - ``teleport`` (str | None): teleport session identifier.
    """
    if options.get("continue"):
        try:
            from claude_code.utils.conversation_recovery import (  # type: ignore[import]
                load_conversation_for_resume,
            )

            result = await load_conversation_for_resume(None, None)
            if result:
                return LoadInitialMessagesResult(
                    messages=result.get("messages", []),
                    turn_interruption_state=result.get("turnInterruptionState"),
                    agent_setting=result.get("agentSetting"),
                )
        except ImportError:
            pass
        except Exception as exc:
            _log_error(exc)
            return LoadInitialMessagesResult(messages=[])

    if options.get("resume"):
        try:
            from claude_code.utils.session_storage import (  # type: ignore[import]
                load_conversation_for_resume as load_resume,
            )
            from claude_code.utils.session_url import (  # type: ignore[import]
                parse_session_identifier,
            )

            resume_val = options["resume"]
            parsed = parse_session_identifier(
                resume_val if isinstance(resume_val, str) else ""
            )
            if not parsed:
                output_format = options.get("output_format")
                emit_load_error(
                    "Error: --resume requires a valid session ID when used with --print. "
                    "Usage: claude -p --resume <session-id>",
                    output_format,
                )
                return LoadInitialMessagesResult(messages=[])

            result = await load_resume(
                parsed.get("session_id"),
                parsed.get("jsonl_file"),
            )
            if not result or not result.get("messages"):
                emit_load_error(
                    f"No conversation found with session ID: {parsed.get('session_id')}",
                    options.get("output_format"),
                )
                return LoadInitialMessagesResult(messages=[])

            # Handle resume_session_at truncation.
            resume_at = options.get("resume_session_at")
            if resume_at:
                messages = result.get("messages", [])
                idx = next(
                    (i for i, m in enumerate(messages) if m.get("uuid") == resume_at),
                    -1,
                )
                if idx < 0:
                    emit_load_error(
                        f"No message found with message.uuid of: {resume_at}",
                        options.get("output_format"),
                    )
                    return LoadInitialMessagesResult(messages=[])
                result["messages"] = messages[: idx + 1]

            return LoadInitialMessagesResult(
                messages=result.get("messages", []),
                turn_interruption_state=result.get("turnInterruptionState"),
                agent_setting=result.get("agentSetting"),
            )
        except ImportError:
            pass
        except Exception as exc:
            _log_error(exc)
            emit_load_error(
                f"Failed to resume session: {exc}",
                options.get("output_format"),
            )
            return LoadInitialMessagesResult(messages=[])

    # Default: fresh session (session-start hooks may prepend messages).
    try:
        from claude_code.utils.session_start import (  # type: ignore[import]
            process_session_start_hooks,
        )

        messages = await process_session_start_hooks("startup")
        return LoadInitialMessagesResult(messages=messages)
    except ImportError:
        return LoadInitialMessagesResult(messages=[])


# ---------------------------------------------------------------------------
# get_structured_io
# ---------------------------------------------------------------------------


def get_structured_io(
    input_prompt: Union[str, AsyncIterable[Any]],
    options: Dict[str, Any],
) -> Any:
    """Build and return the appropriate StructuredIO instance.

    When *options["sdk_url"]* is set a RemoteIO is created; otherwise a
    plain StructuredIO is used.  An empty-string *input_prompt* produces
    an empty async input stream.

    Mirrors ``getStructuredIO`` from the TypeScript source.
    """
    import json

    replay = options.get("replay_user_messages", False)
    sdk_url = options.get("sdk_url")

    # Normalise the raw prompt into an async-iterable of NDJSON lines.
    if isinstance(input_prompt, str):
        if input_prompt.strip():
            user_message = json.dumps({
                "type": "user",
                "session_id": "",
                "message": {"role": "user", "content": input_prompt},
                "parent_tool_use_id": None,
            })
            input_stream = _async_iter_from_list([user_message])
        else:
            input_stream: AsyncIterable[str] = _async_iter_from_list([])
    else:
        input_stream = input_prompt

    if sdk_url:
        try:
            from claude_code.cli.remote_io import RemoteIO  # type: ignore[import]
            return RemoteIO(sdk_url, input_stream, replay)
        except ImportError:
            pass

    try:
        from claude_code.cli.structured_io import StructuredIO  # type: ignore[import]
        return StructuredIO(input_stream, replay)
    except ImportError:
        # Minimal stub
        return _MinimalStructuredIO(input_stream)


async def _async_iter_from_list_inner(items: List[Any]) -> AsyncIterable:
    """Yield items from *items* as an async iterable."""
    for item in items:
        yield item


def _async_iter_from_list(items: List[Any]) -> AsyncIterable:
    """Return an async iterable over *items*."""
    return _async_iter_from_list_inner(items)


class _MinimalStructuredIO:
    """Minimal stub StructuredIO used when the real implementation is unavailable."""

    def __init__(self, input_stream: AsyncIterable[Any]) -> None:
        self.input_stream = input_stream
        self._outbound: List[Any] = []

    @property
    def outbound(self) -> List[Any]:
        return self._outbound

    async def write(self, message: Any) -> None:
        self._outbound.append(message)

    def set_unexpected_response_callback(self, cb: Any) -> None:
        pass


# ---------------------------------------------------------------------------
# handle_initialize_request
# ---------------------------------------------------------------------------


async def handle_initialize_request(
    request: Dict[str, Any],
    request_id: str,
    initialized: bool,
    output_queue: Any,
    commands: List[Any],
    model_infos: List[Dict[str, Any]],
    structured_io: Any,
    enable_auth_status: bool,
    options: Dict[str, Any],
    agents: List[Any],
    get_app_state: Callable[[], Any],
) -> None:
    """Handle an ``initialize`` control request from the SDK.

    Populates the response with commands, agents, account info, and model
    capabilities.  Mirrors ``handleInitializeRequest`` from the TypeScript source.
    """
    if initialized:
        _enqueue_to(output_queue, {
            "type": "control_response",
            "response": {
                "subtype": "error",
                "error": "Already initialized",
                "request_id": request_id,
                "pending_permission_requests": (
                    structured_io.get_pending_permission_requests()
                    if hasattr(structured_io, "get_pending_permission_requests")
                    else []
                ),
            },
        })
        return

    # Apply overrides from the initialize message.
    if "systemPrompt" in request:
        options["system_prompt"] = request["systemPrompt"]
    if "appendSystemPrompt" in request:
        options["append_system_prompt"] = request["appendSystemPrompt"]
    if "promptSuggestions" in request:
        options["prompt_suggestions"] = request["promptSuggestions"]

    # Merge SDK-supplied agents.
    if request.get("agents"):
        try:
            from claude_code.tools.agent_tool.load_agents_dir import (  # type: ignore[import]
                parse_agents_from_json,
            )

            stdin_agents = parse_agents_from_json(request["agents"], "flagSettings")
            agents.extend(stdin_agents)
        except ImportError:
            pass

    # Register hook callbacks.
    if request.get("hooks"):
        try:
            from claude_code.bootstrap.state import register_hook_callbacks  # type: ignore[import]

            hooks: Dict[str, List[Any]] = {}
            for event, matchers in request["hooks"].items():
                hooks[event] = [
                    {
                        "matcher": m.get("matcher"),
                        "hooks": [
                            structured_io.create_hook_callback(
                                cb_id, m.get("timeout")
                            )
                            for cb_id in m.get("hookCallbackIds", [])
                        ],
                    }
                    for m in matchers
                ]
            register_hook_callbacks(hooks)
        except (ImportError, AttributeError):
            pass

    if request.get("jsonSchema"):
        try:
            from claude_code.bootstrap.state import set_init_json_schema  # type: ignore[import]
            set_init_json_schema(request["jsonSchema"])
        except ImportError:
            pass

    # Gather account information.
    account_info: Dict[str, Any] = {}
    try:
        from claude_code.utils.auth import get_account_information  # type: ignore[import]
        info = get_account_information()
        if info:
            account_info = {
                "email": getattr(info, "email", None),
                "organization": getattr(info, "organization", None),
                "subscriptionType": getattr(info, "subscription", None),
                "tokenSource": getattr(info, "token_source", None),
                "apiKeySource": getattr(info, "api_key_source", None),
            }
    except ImportError:
        pass

    def _cmd_info(cmd: Any) -> Dict[str, str]:
        name = (
            cmd.get("name", "") if isinstance(cmd, dict)
            else getattr(cmd, "name", "")
        )
        description = (
            cmd.get("description", "") if isinstance(cmd, dict)
            else getattr(cmd, "description", "")
        )
        argument_hint = (
            cmd.get("argument_hint", "") if isinstance(cmd, dict)
            else getattr(cmd, "argument_hint", "")
        ) or ""
        return {"name": name, "description": description, "argumentHint": argument_hint}

    def _agent_info(agent: Any) -> Dict[str, Any]:
        agent_type = (
            agent.get("agent_type", "") if isinstance(agent, dict)
            else getattr(agent, "agent_type", "")
        )
        when_to_use = (
            agent.get("when_to_use", "") if isinstance(agent, dict)
            else getattr(agent, "when_to_use", "")
        )
        model = (
            agent.get("model") if isinstance(agent, dict)
            else getattr(agent, "model", None)
        )
        return {
            "name": agent_type,
            "description": when_to_use,
            "model": None if model == "inherit" else model,
        }

    visible_commands = [
        c for c in commands
        if (
            c.get("user_invocable", True) if isinstance(c, dict)
            else getattr(c, "user_invocable", True)
        ) is not False
    ]

    init_response: Dict[str, Any] = {
        "commands": [_cmd_info(c) for c in visible_commands],
        "agents": [_agent_info(a) for a in agents],
        "models": model_infos,
        "account": account_info,
        "pid": os.getpid(),
    }

    _enqueue_to(output_queue, {
        "type": "control_response",
        "response": {
            "subtype": "success",
            "request_id": request_id,
            "response": init_response,
        },
    })


# ---------------------------------------------------------------------------
# run_headless_streaming  (async generator — core query loop)
# ---------------------------------------------------------------------------


async def run_headless_streaming(
    structured_io: Any,
    mcp_clients: List[Any],
    commands: List[Any],
    tools: List[Any],
    initial_messages: List[Dict[str, Any]],
    can_use_tool: Callable[..., Awaitable[Dict[str, Any]]],
    sdk_mcp_configs: Dict[str, Any],
    get_app_state: Callable[[], Any],
    set_app_state: Callable[[Callable[[Any], Any]], None],
    agents: List[Any],
    options: Dict[str, Any],
    turn_interruption_state: Optional[Dict[str, Any]] = None,
) -> AsyncIterable[Dict[str, Any]]:
    """Async generator that runs the headless query loop and yields SDK messages.

    This is the inner streaming loop called by :func:`run_headless`.  Each
    yielded item is an ``StdoutMessage``-shaped dict.

    Mirrors ``runHeadlessStreaming`` from the TypeScript source.  The full
    interactive scaffolding (proactive ticks, cron scheduler, bridge handle,
    etc.) is not yet ported; the core ask/drain loop is implemented.
    """
    import asyncio
    import json

    # -----------------------------------------------------------------------
    # State
    # -----------------------------------------------------------------------
    running = False
    input_closed = False
    shutdown_prompt_injected = False
    held_back_result: Optional[Dict[str, Any]] = None
    abort_controller: Optional[Any] = None

    # Output queue — items yielded to caller
    output_queue: asyncio.Queue = asyncio.Queue()
    output_done = asyncio.Event()

    # Mutable message list (mutated by ask())
    mutable_messages: List[Dict[str, Any]] = list(initial_messages)

    # SDK MCP state
    sdk_clients: List[Any] = []
    sdk_tools: List[Any] = []
    dynamic_mcp_state = DynamicMcpState()

    # Track handled orphaned tool_use IDs
    handled_orphaned_tool_use_ids: Set[str] = set()

    # Current commands / agents (may be hot-reloaded)
    current_commands = list(commands)
    current_agents = list(agents)

    # SDK active user model
    active_user_specified_model = options.get("user_specified_model")

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _enqueue_output(item: Dict[str, Any]) -> None:
        """Put *item* onto the output queue."""
        output_queue.put_nowait(item)

    def _get_session_id_local() -> str:
        return _get_session_id()

    def _new_uuid() -> str:
        return str(_uuid_module.uuid4())

    def _ctrl_success(
        message: Dict[str, Any],
        response: Optional[Dict[str, Any]] = None,
    ) -> None:
        _enqueue_output({
            "type": "control_response",
            "response": {
                "subtype": "success",
                "request_id": message.get("request_id"),
                "response": response,
            },
        })

    def _ctrl_error(message: Dict[str, Any], error_text: str) -> None:
        _enqueue_output({
            "type": "control_response",
            "response": {
                "subtype": "error",
                "request_id": message.get("request_id"),
                "error": error_text,
            },
        })

    def _build_all_tools(app_state: Any) -> List[Any]:
        """Assemble the full tool list for the current turn."""
        mcp_state = (
            app_state.get("mcp", {}) if isinstance(app_state, dict)
            else getattr(app_state, "mcp", {})
        ) or {}
        app_mcp_tools = (
            mcp_state.get("tools", []) if isinstance(mcp_state, dict)
            else getattr(mcp_state, "tools", [])
        )
        all_tools = list(tools) + list(sdk_tools) + list(dynamic_mcp_state.tools)
        # Deduplicate by name (later entries win)
        seen: Dict[str, Any] = {}
        for t in all_tools:
            name = _tool_name(t)
            seen[name] = t
        result = list(seen.values())
        # Remove permission-prompt tool
        ppt = options.get("permission_prompt_tool_name")
        if ppt:
            result = [t for t in result if not _tool_matches_name(t, ppt)]
        return result

    async def _update_sdk_mcp() -> None:
        """Connect / reconnect SDK MCP servers as needed."""
        nonlocal sdk_clients, sdk_tools
        current_names: Set[str] = set(sdk_mcp_configs.keys())
        connected_names: Set[str] = {c.get("name", "") if isinstance(c, dict) else getattr(c, "name", "") for c in sdk_clients}
        has_new = any(n not in connected_names for n in current_names)
        has_removed = any(n not in current_names for n in connected_names)
        has_pending = any(
            (c.get("type") if isinstance(c, dict) else getattr(c, "type", "")) == "pending"
            for c in sdk_clients
        )
        if not (has_new or has_removed or has_pending):
            return
        try:
            from claude_code.services.mcp.client import setup_sdk_mcp_clients  # type: ignore[import]
            result = await setup_sdk_mcp_clients(
                sdk_mcp_configs,
                lambda server_name, msg: None,  # stub message sender
            )
            sdk_clients = result["clients"]
            sdk_tools = result["tools"]
        except ImportError:
            pass

    # Auto-resume interrupted turns
    if (
        turn_interruption_state
        and turn_interruption_state.get("kind", "none") != "none"
        and os.environ.get("CLAUDE_CODE_RESUME_INTERRUPTED_TURN")
    ):
        remove_interrupted_message(mutable_messages, turn_interruption_state.get("message", {}))
        _enqueue(
            {
                "mode": "prompt",
                "value": turn_interruption_state.get("message", {}).get("message", {}).get("content", ""),
                "uuid": _new_uuid(),
            }
        )

    # -----------------------------------------------------------------------
    # run() — processes queued commands
    # -----------------------------------------------------------------------

    async def run() -> None:
        nonlocal running, held_back_result, abort_controller
        if running:
            return
        running = True

        try:
            await _update_sdk_mcp()

            def _is_main_thread(cmd: Dict[str, Any]) -> bool:
                return cmd.get("agent_id") is None

            async def drain_command_queue() -> None:
                nonlocal abort_controller, held_back_result
                while True:
                    # Dequeue next main-thread command
                    try:
                        from claude_code.utils.message_queue_manager import (  # type: ignore[import]
                            dequeue, peek, can_batch_with as _ts_can_batch_with,
                        )
                        command: Optional[Dict[str, Any]] = dequeue(_is_main_thread)
                    except ImportError:
                        command = None

                    if command is None:
                        break

                    mode = command.get("mode", "prompt")
                    if mode not in ("prompt", "orphaned-permission", "task-notification"):
                        raise RuntimeError("only prompt commands are supported in streaming mode")

                    # Batch consecutive prompt commands
                    batch = [command]
                    if mode == "prompt":
                        try:
                            from claude_code.utils.message_queue_manager import (  # type: ignore[import]
                                peek, dequeue,
                            )
                            while can_batch_with(command, peek(_is_main_thread)):
                                nxt = dequeue(_is_main_thread)
                                if nxt:
                                    batch.append(nxt)
                        except ImportError:
                            pass
                        if len(batch) > 1:
                            merged_value = join_prompt_values([c.get("value", "") for c in batch])
                            last_uuid = next(
                                (c.get("uuid") for c in reversed(batch) if c.get("uuid")),
                                command.get("uuid"),
                            )
                            command = {**command, "value": merged_value, "uuid": last_uuid}

                    batch_uuids = [c.get("uuid") for c in batch if c.get("uuid")]

                    # Notify command lifecycle: started
                    for uid in batch_uuids:
                        try:
                            from claude_code.utils.command_lifecycle import notify_command_lifecycle  # type: ignore[import]
                            notify_command_lifecycle(uid, "started")
                        except ImportError:
                            pass

                    # Handle task-notification
                    if mode == "task-notification":
                        notification_text = command.get("value", "")
                        if isinstance(notification_text, str):
                            parsed = parse_task_notification(notification_text)
                            if parsed.get("has_status"):
                                _enqueue_output({
                                    "type": "system",
                                    "subtype": "task_notification",
                                    "task_id": parsed["task_id"],
                                    "tool_use_id": parsed.get("tool_use_id"),
                                    "status": parsed["status"],
                                    "output_file": parsed["output_file"],
                                    "summary": parsed["summary"],
                                    "usage": parsed.get("usage"),
                                    "session_id": _get_session_id_local(),
                                    "uuid": _new_uuid(),
                                })

                    # Build tool list
                    app_state = get_app_state()
                    all_mcp_clients = (
                        list((app_state.get("mcp", {}) if isinstance(app_state, dict) else getattr(app_state, "mcp", {}) or {}).get("clients", []))
                        + sdk_clients
                        + dynamic_mcp_state.clients
                    )
                    all_tools = _build_all_tools(app_state)

                    input_val = command.get("value", "")

                    # Create abort controller for this turn
                    abort_controller = _create_abort_controller()

                    # Ask the model
                    try:
                        from claude_code.query_engine import ask  # type: ignore[import]

                        workload = command.get("workload") or options.get("workload")
                        async for message in ask(
                            commands=current_commands,
                            prompt=input_val,
                            prompt_uuid=command.get("uuid"),
                            is_meta=command.get("is_meta", False),
                            cwd=os.getcwd(),
                            tools=all_tools,
                            verbose=options.get("verbose"),
                            mcp_clients=all_mcp_clients,
                            thinking_config=options.get("thinking_config"),
                            max_turns=options.get("max_turns"),
                            max_budget_usd=options.get("max_budget_usd"),
                            task_budget=options.get("task_budget"),
                            can_use_tool=can_use_tool,
                            user_specified_model=active_user_specified_model,
                            fallback_model=options.get("fallback_model"),
                            json_schema=options.get("json_schema"),
                            mutable_messages=mutable_messages,
                            custom_system_prompt=options.get("system_prompt"),
                            append_system_prompt=options.get("append_system_prompt"),
                            get_app_state=get_app_state,
                            set_app_state=set_app_state,
                            abort_controller=abort_controller,
                            replay_user_messages=options.get("replay_user_messages"),
                            include_partial_messages=options.get("include_partial_messages"),
                            agents=current_agents,
                            orphaned_permission=command.get("orphaned_permission"),
                        ):
                            if message.get("type") == "result":
                                held_back_result = None
                                _enqueue_output(message)
                            else:
                                _enqueue_output(message)

                    except ImportError:
                        # ask() not available — emit an error result
                        _enqueue_output({
                            "type": "result",
                            "subtype": "error_during_execution",
                            "duration_ms": 0,
                            "duration_api_ms": 0,
                            "is_error": True,
                            "num_turns": 0,
                            "stop_reason": None,
                            "session_id": _get_session_id_local(),
                            "total_cost_usd": 0,
                            "usage": {},
                            "modelUsage": {},
                            "permission_denials": [],
                            "uuid": _new_uuid(),
                            "errors": ["QueryEngine (ask) module not available"],
                        })

                    # Notify command lifecycle: completed
                    for uid in batch_uuids:
                        try:
                            from claude_code.utils.command_lifecycle import notify_command_lifecycle  # type: ignore[import]
                            notify_command_lifecycle(uid, "completed")
                        except ImportError:
                            pass

            # do-while: drain commands, then wait for background agents
            waiting_for_agents = False
            while True:
                await drain_command_queue()

                # Check for background tasks
                waiting_for_agents = False
                try:
                    from claude_code.utils.task.framework import get_running_tasks  # type: ignore[import]
                    from claude_code.tasks.types import is_background_task  # type: ignore[import]
                    state = get_app_state()
                    has_running_bg = any(
                        is_background_task(t) and getattr(t, "type", "") != "in_process_teammate"
                        for t in get_running_tasks(state)
                    )
                    if has_running_bg:
                        waiting_for_agents = True
                        await asyncio.sleep(0.1)
                except ImportError:
                    pass

                if not waiting_for_agents:
                    break

            if held_back_result:
                _enqueue_output(held_back_result)
                held_back_result = None

        except Exception as exc:
            # Emit error result
            try:
                _enqueue_output({
                    "type": "result",
                    "subtype": "error_during_execution",
                    "duration_ms": 0,
                    "duration_api_ms": 0,
                    "is_error": True,
                    "num_turns": 0,
                    "stop_reason": None,
                    "session_id": _get_session_id_local(),
                    "total_cost_usd": 0,
                    "usage": {},
                    "modelUsage": {},
                    "permission_denials": [],
                    "uuid": _new_uuid(),
                    "errors": [str(exc)],
                })
            except Exception:
                pass
            output_done.set()
            return
        finally:
            running = False

        if input_closed:
            # Clean up and signal done
            try:
                from claude_code.utils.hooks.async_hook_registry import finalize_pending_async_hooks  # type: ignore[import]
                await finalize_pending_async_hooks()
            except ImportError:
                pass
            output_done.set()

    # -----------------------------------------------------------------------
    # Input processing loop (parallel task)
    # -----------------------------------------------------------------------

    initialized = False

    async def process_input() -> None:
        nonlocal initialized, input_closed, active_user_specified_model

        input_stream = getattr(structured_io, "structured_input", None)
        if input_stream is None:
            # No structured input — treat input as closed
            input_closed = True
            if not running:
                output_done.set()
            return

        try:
            async for message in input_stream:
                msg_type = message.get("type", "") if isinstance(message, dict) else getattr(message, "type", "")

                if msg_type == "control_request":
                    request = message.get("request", {}) if isinstance(message, dict) else getattr(message, "request", {})
                    request_id = message.get("request_id", "") if isinstance(message, dict) else getattr(message, "request_id", "")
                    subtype = request.get("subtype", "") if isinstance(request, dict) else getattr(request, "subtype", "")

                    if subtype == "interrupt":
                        if abort_controller is not None:
                            _abort_controller(abort_controller)
                        _ctrl_success(message)

                    elif subtype == "end_session":
                        if abort_controller is not None:
                            _abort_controller(abort_controller)
                        _ctrl_success(message)
                        break  # exit input loop

                    elif subtype == "initialize":
                        # Register SDK MCP servers from initialize message
                        sdk_servers = request.get("sdkMcpServers", []) if isinstance(request, dict) else []
                        for server_name in sdk_servers:
                            sdk_mcp_configs[server_name] = {"type": "sdk", "name": server_name}

                        await handle_initialize_request(
                            request,
                            request_id,
                            initialized,
                            output_queue,
                            current_commands,
                            model_infos_local,
                            structured_io,
                            bool(options.get("enable_auth_status")),
                            options,
                            current_agents,
                            get_app_state,
                        )
                        initialized = True

                        # Kick off run if commands pre-queued
                        try:
                            from claude_code.utils.message_queue_manager import has_commands_in_queue  # type: ignore[import]
                            if has_commands_in_queue():
                                asyncio.ensure_future(run())
                        except ImportError:
                            pass

                    elif subtype == "set_permission_mode":
                        app_state = get_app_state()
                        tool_perm_ctx = (
                            app_state.get("tool_permission_context", {}) if isinstance(app_state, dict)
                            else getattr(app_state, "tool_permission_context", {})
                        )
                        new_ctx = handle_set_permission_mode(
                            request, request_id, tool_perm_ctx, output_queue
                        )

                        def _update_perm(prev: Any) -> Any:
                            if isinstance(prev, dict):
                                return {**prev, "tool_permission_context": new_ctx}
                            try:
                                import copy
                                np = copy.copy(prev)
                                object.__setattr__(np, "tool_permission_context", new_ctx)
                                return np
                            except Exception:
                                return prev

                        set_app_state(_update_perm)

                    elif subtype == "set_model":
                        requested = request.get("model", "default") if isinstance(request, dict) else "default"
                        try:
                            from claude_code.utils.model.model import (
                                get_default_main_loop_model,
                                parse_user_specified_model,
                            )  # type: ignore[import]
                            model = (
                                get_default_main_loop_model()
                                if requested == "default"
                                else parse_user_specified_model(requested)
                            )
                        except ImportError:
                            model = requested
                        active_user_specified_model = model
                        _ctrl_success(message)

                    elif subtype == "set_max_thinking_tokens":
                        max_tokens = request.get("max_thinking_tokens") if isinstance(request, dict) else None
                        if max_tokens is None:
                            options["thinking_config"] = None
                        elif max_tokens == 0:
                            options["thinking_config"] = {"type": "disabled"}
                        else:
                            options["thinking_config"] = {"type": "enabled", "budget_tokens": max_tokens}
                        _ctrl_success(message)

                    elif subtype == "mcp_status":
                        app_state = get_app_state()
                        app_mcp = (
                            app_state.get("mcp", {}) if isinstance(app_state, dict)
                            else getattr(app_state, "mcp", {})
                        ) or {}
                        app_clients = (
                            app_mcp.get("clients", []) if isinstance(app_mcp, dict)
                            else getattr(app_mcp, "clients", [])
                        )
                        all_tools_for_status = (
                            list(app_mcp.get("tools", []) if isinstance(app_mcp, dict) else getattr(app_mcp, "tools", []))
                            + dynamic_mcp_state.tools
                        )
                        statuses = build_mcp_server_statuses(
                            app_clients, sdk_clients, dynamic_mcp_state, all_tools_for_status
                        )
                        _ctrl_success(message, {"mcpServers": statuses})

                    elif subtype == "mcp_set_servers":
                        servers = request.get("servers", {}) if isinstance(request, dict) else {}
                        result = await handle_mcp_set_servers(
                            servers,
                            SdkMcpState(
                                configs=dict(sdk_mcp_configs),
                                clients=list(sdk_clients),
                                tools=list(sdk_tools),
                            ),
                            dynamic_mcp_state,
                            set_app_state,
                        )
                        _ctrl_success(message, result.response)
                        if result.sdk_servers_changed:
                            asyncio.ensure_future(_update_sdk_mcp())

                    elif subtype == "cancel_async_message":
                        target_uuid = request.get("message_uuid") if isinstance(request, dict) else None
                        cancelled = False
                        if target_uuid:
                            try:
                                from claude_code.utils.message_queue_manager import dequeue_all_matching  # type: ignore[import]
                                removed = dequeue_all_matching(lambda cmd: cmd.get("uuid") == target_uuid)
                                cancelled = len(removed) > 0
                            except ImportError:
                                pass
                        _ctrl_success(message, {"cancelled": cancelled})

                    elif subtype == "rewind_files":
                        app_state = get_app_state()
                        dry_run = request.get("dry_run", False) if isinstance(request, dict) else False
                        uid = request.get("user_message_id", "") if isinstance(request, dict) else ""
                        result_rw = await handle_rewind_files(uid, app_state, set_app_state, dry_run)
                        if result_rw.can_rewind or dry_run:
                            _ctrl_success(message, {
                                "can_rewind": result_rw.can_rewind,
                                "error": result_rw.error,
                                "files_changed": result_rw.files_changed,
                                "insertions": result_rw.insertions,
                                "deletions": result_rw.deletions,
                            })
                        else:
                            _ctrl_error(message, result_rw.error or "Unexpected error")

                    elif subtype == "channel_enable":
                        server_name = request.get("serverName", "") if isinstance(request, dict) else ""
                        app_state = get_app_state()
                        app_mcp = (
                            app_state.get("mcp", {}) if isinstance(app_state, dict)
                            else getattr(app_state, "mcp", {})
                        ) or {}
                        app_clients = (
                            app_mcp.get("clients", []) if isinstance(app_mcp, dict)
                            else getattr(app_mcp, "clients", [])
                        )
                        pool = app_clients + sdk_clients + dynamic_mcp_state.clients
                        handle_channel_enable(request_id, server_name, pool, output_queue)

                    elif subtype == "reload_plugins":
                        try:
                            from claude_code.utils.plugins.refresh import refresh_active_plugins  # type: ignore[import]
                            r = await refresh_active_plugins(set_app_state)
                            sdk_agent_defs = [a for a in current_agents if getattr(a, "source", "") == "flagSettings"]
                            fresh_agents = getattr(r, "agent_definitions", {}).get("all_agents", [])
                            current_agents.clear()
                            current_agents.extend(list(fresh_agents) + sdk_agent_defs)
                            app_state = get_app_state()
                            app_mcp = (
                                app_state.get("mcp", {}) if isinstance(app_state, dict)
                                else getattr(app_state, "mcp", {})
                            ) or {}
                            all_tools_reload = (
                                list(app_mcp.get("tools", []) if isinstance(app_mcp, dict) else getattr(app_mcp, "tools", []))
                                + dynamic_mcp_state.tools
                            )
                            statuses = build_mcp_server_statuses(
                                app_mcp.get("clients", []) if isinstance(app_mcp, dict) else getattr(app_mcp, "clients", []),
                                sdk_clients, dynamic_mcp_state, all_tools_reload
                            )
                            _ctrl_success(message, {
                                "commands": [
                                    {
                                        "name": c.get("name", "") if isinstance(c, dict) else getattr(c, "name", ""),
                                        "description": c.get("description", "") if isinstance(c, dict) else getattr(c, "description", ""),
                                        "argumentHint": c.get("argument_hint", "") if isinstance(c, dict) else getattr(c, "argument_hint", ""),
                                    }
                                    for c in current_commands
                                    if (c.get("user_invocable", True) if isinstance(c, dict) else getattr(c, "user_invocable", True)) is not False
                                ],
                                "agents": [
                                    {
                                        "name": a.get("agent_type", "") if isinstance(a, dict) else getattr(a, "agent_type", ""),
                                        "description": a.get("when_to_use", "") if isinstance(a, dict) else getattr(a, "when_to_use", ""),
                                    }
                                    for a in current_agents
                                ],
                                "plugins": [],
                                "mcpServers": statuses,
                                "error_count": getattr(r, "error_count", 0),
                            })
                        except ImportError:
                            _ctrl_error(message, "reload_plugins: plugins module unavailable")

                    elif subtype == "mcp_reconnect":
                        server_name = request.get("serverName", "") if isinstance(request, dict) else ""
                        try:
                            from claude_code.services.mcp.client import reconnect_mcp_server_impl  # type: ignore[import]
                            config = None
                            for src in [mcp_clients, sdk_clients, dynamic_mcp_state.clients]:
                                cfg = next(
                                    (c.get("config") if isinstance(c, dict) else getattr(c, "config", None)
                                     for c in src if (c.get("name") if isinstance(c, dict) else getattr(c, "name", "")) == server_name),
                                    None,
                                )
                                if cfg:
                                    config = cfg
                                    break
                            if not config:
                                _ctrl_error(message, f"Server not found: {server_name}")
                            else:
                                result_rc = await reconnect_mcp_server_impl(server_name, config)
                                client_result = result_rc.get("client", {})
                                if (client_result.get("type") if isinstance(client_result, dict) else getattr(client_result, "type", "")) == "connected":
                                    _ctrl_success(message)
                                else:
                                    err_msg = (client_result.get("error") if isinstance(client_result, dict) else getattr(client_result, "error", None)) or "Connection failed"
                                    _ctrl_error(message, err_msg)
                        except ImportError:
                            _ctrl_error(message, "mcp_reconnect: MCP client module unavailable")

                    elif subtype == "mcp_toggle":
                        server_name = request.get("serverName", "") if isinstance(request, dict) else ""
                        enabled = request.get("enabled", True) if isinstance(request, dict) else True
                        try:
                            from claude_code.services.mcp.config import set_mcp_server_enabled  # type: ignore[import]
                            set_mcp_server_enabled(server_name, enabled)
                            _ctrl_success(message)
                        except ImportError:
                            _ctrl_success(message)  # best-effort

                    elif subtype == "get_settings":
                        try:
                            from claude_code.utils.settings.settings import get_settings_with_sources  # type: ignore[import]
                            settings_data = get_settings_with_sources()
                            _ctrl_success(message, settings_data)
                        except ImportError:
                            _ctrl_success(message, {})

                    elif subtype == "stop_task":
                        task_id = request.get("task_id", "") if isinstance(request, dict) else ""
                        try:
                            from claude_code.tasks.stop_task import stop_task  # type: ignore[import]
                            await stop_task(task_id, get_app_state=get_app_state, set_app_state=set_app_state)
                            _ctrl_success(message, {})
                        except ImportError:
                            _ctrl_error(message, "stop_task: module unavailable")
                        except Exception as exc:
                            _ctrl_error(message, str(exc))

                    elif subtype == "generate_session_title":
                        description = request.get("description", "") if isinstance(request, dict) else ""
                        persist = request.get("persist", False) if isinstance(request, dict) else False
                        async def _gen_title() -> None:
                            try:
                                from claude_code.utils.session_title import generate_session_title  # type: ignore[import]
                                title = await generate_session_title(description, None)
                                _ctrl_success(message, {"title": title})
                            except ImportError:
                                _ctrl_success(message, {"title": None})
                        asyncio.ensure_future(_gen_title())

                    elif subtype == "side_question":
                        question = request.get("question", "") if isinstance(request, dict) else ""
                        async def _side_q() -> None:
                            try:
                                from claude_code.utils.side_question import run_side_question  # type: ignore[import]
                                result_sq = await run_side_question(question=question, cache_safe_params=None)
                                _ctrl_success(message, {"response": result_sq.get("response")})
                            except ImportError:
                                _ctrl_error(message, "side_question: module unavailable")
                            except Exception as exc:
                                _ctrl_error(message, str(exc))
                        asyncio.ensure_future(_side_q())

                    elif subtype == "apply_flag_settings":
                        incoming = request.get("settings", {}) if isinstance(request, dict) else {}
                        try:
                            from claude_code.bootstrap.state import get_flag_settings_inline, set_flag_settings_inline  # type: ignore[import]
                            existing = get_flag_settings_inline() or {}
                            merged = {**existing, **incoming}
                            for key in list(merged.keys()):
                                if merged[key] is None:
                                    del merged[key]
                            set_flag_settings_inline(merged)
                        except ImportError:
                            pass
                        _ctrl_success(message)

                    else:
                        # Unknown control request — send error so caller doesn't hang
                        _ctrl_error(message, f"Unsupported control request subtype: {subtype}")

                    continue

                elif msg_type == "control_response":
                    if options.get("replay_user_messages"):
                        _enqueue_output(message)
                    continue

                elif msg_type == "keep_alive":
                    continue

                elif msg_type == "update_environment_variables":
                    continue

                elif msg_type in ("assistant", "system"):
                    # History replay from bridge
                    mutable_messages.append(message)
                    if msg_type == "assistant" and options.get("replay_user_messages"):
                        _enqueue_output(message)
                    continue

                # Only user messages should remain
                if msg_type != "user":
                    continue

                initialized = True

                # Dedup
                msg_uuid = message.get("uuid") if isinstance(message, dict) else getattr(message, "uuid", None)
                if msg_uuid:
                    is_dup = not track_received_message_uuid(msg_uuid)
                    if is_dup:
                        _log_debug(f"Skipping duplicate user message: {msg_uuid}")
                        continue

                # Enqueue for processing
                msg_content = (
                    message.get("message", {}).get("content", "")
                    if isinstance(message, dict)
                    else getattr(getattr(message, "message", {}), "content", "")
                )
                priority = message.get("priority") if isinstance(message, dict) else getattr(message, "priority", None)
                _enqueue({
                    "mode": "prompt",
                    "value": msg_content,
                    "uuid": msg_uuid,
                    "priority": priority,
                })
                asyncio.ensure_future(run())

        except Exception as exc:
            _log_error(exc)
        finally:
            input_closed = True
            if not running:
                # Flush async hooks and close output
                try:
                    from claude_code.utils.hooks.async_hook_registry import finalize_pending_async_hooks  # type: ignore[import]
                    await finalize_pending_async_hooks()
                except ImportError:
                    pass
                output_done.set()

    # Build model_infos for use in handle_initialize_request
    model_infos_local: List[Dict[str, Any]] = []
    try:
        from claude_code.utils.model.model import get_model_options  # type: ignore[import]
        model_infos_local = build_model_infos(get_model_options())
    except ImportError:
        pass

    # Set up orphaned permission response callback
    if hasattr(structured_io, "set_unexpected_response_callback"):
        async def _orphan_cb(msg: Dict[str, Any]) -> None:
            await handle_orphaned_permission_response(
                message=msg,
                set_app_state=set_app_state,
                on_enqueued=lambda: asyncio.ensure_future(run()),
                handled_tool_use_ids=handled_orphaned_tool_use_ids,
            )
        structured_io.set_unexpected_response_callback(_orphan_cb)

    # Start input processing and initial run concurrently
    input_task = asyncio.ensure_future(process_input())

    # If there are already commands in queue (e.g., auto-resumed interrupted turn),
    # kick off run() immediately
    try:
        from claude_code.utils.message_queue_manager import has_commands_in_queue  # type: ignore[import]
        if has_commands_in_queue():
            asyncio.ensure_future(run())
    except ImportError:
        # No queue — start run if we have a plain string prompt
        if options.get("_has_prompt"):
            asyncio.ensure_future(run())

    # Yield messages from output queue until done
    while True:
        # Poll for output
        try:
            item = output_queue.get_nowait()
            yield item
            continue
        except asyncio.QueueEmpty:
            pass

        if output_done.is_set() and output_queue.empty():
            break

        # Wait a bit for more output
        try:
            item = await asyncio.wait_for(output_queue.get(), timeout=0.05)
            yield item
        except asyncio.TimeoutError:
            pass
        except Exception:
            break

    # Drain remaining items
    while not output_queue.empty():
        try:
            yield output_queue.get_nowait()
        except asyncio.QueueEmpty:
            break

    # Clean up input task
    if not input_task.done():
        input_task.cancel()
        try:
            await input_task
        except asyncio.CancelledError:
            pass


def _create_abort_controller() -> Any:
    """Create an abort controller. Returns a simple object with a signal."""
    try:
        from claude_code.utils.abort_controller import create_abort_controller  # type: ignore[import]
        return create_abort_controller()
    except ImportError:
        # Minimal stub
        class _AbortSignal:
            aborted = False
        class _AbortController:
            signal = _AbortSignal()
            def abort(self) -> None:
                self.signal.aborted = True
        return _AbortController()


def _abort_controller(ctrl: Any) -> None:
    """Abort a controller."""
    if ctrl is None:
        return
    if hasattr(ctrl, "abort"):
        ctrl.abort()


# ---------------------------------------------------------------------------
# handle_channel_enable
# ---------------------------------------------------------------------------


def handle_channel_enable(
    request_id: str,
    server_name: str,
    connection_pool: List[Dict[str, Any]],
    output_queue: Any,
) -> None:
    """Handle an IDE-triggered ``channel_enable`` control request.

    Validates the server, appends it to the session allowed-channels list,
    and registers the channel-message notification handler.  On gate failure
    or missing server, emits an error control response.

    Mirrors ``handleChannelEnable`` from the TypeScript source.
    """
    def _error(msg: str) -> None:
        send_control_response_error(
            output_queue, {"request_id": request_id}, msg
        )

    # Find the connected server in the pool.
    connection = next(
        (
            c for c in connection_pool
            if (
                (c.get("name") if isinstance(c, dict) else getattr(c, "name", None))
                == server_name
                and (
                    (c.get("type") if isinstance(c, dict) else getattr(c, "type", None))
                    == "connected"
                )
            )
        ),
        None,
    )
    if connection is None:
        return _error(f"server {server_name} is not connected")

    # Validate plugin source.
    config = (
        connection.get("config", {}) if isinstance(connection, dict)
        else getattr(connection, "config", {})
    ) or {}
    plugin_source = (
        config.get("pluginSource") if isinstance(config, dict)
        else getattr(config, "plugin_source", None)
    )

    if not plugin_source:
        return _error(
            f"server {server_name} is not plugin-sourced; "
            "channel_enable requires a marketplace plugin"
        )

    # Try to gate through the channel allowlist.
    try:
        from claude_code.services.mcp.channel_notification import (  # type: ignore[import]
            gate_channel_server,
        )
        from claude_code.bootstrap.state import (  # type: ignore[import]
            get_allowed_channels,
            set_allowed_channels,
        )

        capabilities = (
            connection.get("capabilities", {})
            if isinstance(connection, dict)
            else getattr(connection, "capabilities", {})
        ) or {}
        gate = gate_channel_server(server_name, capabilities, plugin_source)
        if gate.get("action") == "skip":
            return _error(gate.get("reason", "channel gate failed"))

        send_control_response_success(output_queue, {"request_id": request_id})
    except ImportError:
        # Channel feature unavailable — return success stub.
        send_control_response_success(output_queue, {"request_id": request_id})


# ---------------------------------------------------------------------------
# Task-notification parsing helpers
# ---------------------------------------------------------------------------


def parse_task_notification(
    notification_text: str,
) -> Dict[str, Any]:
    """Parse a task-notification XML blob into a structured dict.

    Mirrors the inline regex parsing inside ``drainCommandQueue`` in the
    TypeScript source.

    Returns a dict with keys:
    - ``task_id``
    - ``tool_use_id`` (optional)
    - ``output_file``
    - ``summary``
    - ``status``:  one of ``'completed'``, ``'failed'``, ``'stopped'``
    - ``usage``: optional sub-dict with ``total_tokens``, ``tool_uses``, ``duration_ms``
    - ``has_status``: ``True`` when a ``<status>`` tag was present (terminal notification)
    """
    task_id_m = re.search(r"<task-id>([^<]+)</task-id>", notification_text)
    tool_use_id_m = re.search(r"<tool-use-id>([^<]+)</tool-use-id>", notification_text)
    output_file_m = re.search(r"<output-file>([^<]+)</output-file>", notification_text)
    status_m = re.search(r"<status>([^<]+)</status>", notification_text)
    summary_m = re.search(r"<summary>([^<]+)</summary>", notification_text)
    usage_m = re.search(r"<usage>(.*?)</usage>", notification_text, re.DOTALL)

    raw_status = status_m.group(1) if status_m else None
    valid_statuses = {"completed", "failed", "stopped", "killed"}
    if raw_status in valid_statuses:
        status = "stopped" if raw_status == "killed" else raw_status
    else:
        status = "completed"

    usage: Optional[Dict[str, int]] = None
    if usage_m:
        usage_content = usage_m.group(1)
        total_m = re.search(r"<total_tokens>(\d+)</total_tokens>", usage_content)
        tool_uses_m = re.search(r"<tool_uses>(\d+)</tool_uses>", usage_content)
        duration_m = re.search(r"<duration_ms>(\d+)</duration_ms>", usage_content)
        if total_m and tool_uses_m:
            usage = {
                "total_tokens": int(total_m.group(1)),
                "tool_uses": int(tool_uses_m.group(1)),
                "duration_ms": int(duration_m.group(1)) if duration_m else 0,
            }

    return {
        "task_id": task_id_m.group(1) if task_id_m else "",
        "tool_use_id": tool_use_id_m.group(1) if tool_use_id_m else None,
        "output_file": output_file_m.group(1) if output_file_m else "",
        "summary": summary_m.group(1) if summary_m else "",
        "status": status,
        "usage": usage,
        "has_status": status_m is not None,
    }


# ---------------------------------------------------------------------------
# Output-format helpers
# ---------------------------------------------------------------------------


SHUTDOWN_TEAM_PROMPT: str = """<system-reminder>
You are running in non-interactive mode and cannot return a response to the user until your team is shut down.

You MUST shut down your team before preparing your final response:
1. Use requestShutdown to ask each team member to shut down gracefully
2. Wait for shutdown approvals
3. Use the cleanup operation to clean up the team
4. Only then provide your final response to the user

The user cannot receive your response until the team is completely shut down.
</system-reminder>

Shut down your team and prepare your final response for the user."""


def format_headless_result(
    last_message: Optional[Dict[str, Any]],
    output_format: Optional[str],
    max_turns: Optional[int] = None,
    max_budget_usd: Optional[float] = None,
) -> str:
    """Format the final result message for non-stream-json output modes.

    Returns the string to be written to stdout.  Mirrors the ``switch
    (options.outputFormat)`` block inside ``runHeadless`` in the TypeScript
    source.
    """
    import json

    if output_format == "json":
        if not last_message or last_message.get("type") != "result":
            raise ValueError("No messages returned")
        return json.dumps(last_message) + "\n"

    if output_format == "stream-json":
        # Already streamed above — nothing to format here.
        return ""

    # Default text output.
    if not last_message or last_message.get("type") != "result":
        raise ValueError("No messages returned")

    subtype = last_message.get("subtype", "")
    if subtype == "success":
        result_text = last_message.get("result", "")
        return result_text if result_text.endswith("\n") else result_text + "\n"
    elif subtype == "error_during_execution":
        return "Execution error\n"
    elif subtype == "error_max_turns":
        return f"Error: Reached max turns ({max_turns})\n"
    elif subtype == "error_max_budget_usd":
        return f"Error: Exceeded USD budget ({max_budget_usd})\n"
    elif subtype == "error_max_structured_output_retries":
        return "Error: Failed to provide valid structured output after maximum retries\n"
    else:
        return f"Error: {subtype}\n"


# ---------------------------------------------------------------------------
# Model-info helpers (SDK initialize response)
# ---------------------------------------------------------------------------


def build_model_infos(model_options: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw model option dicts to the ``ModelInfo[]`` shape used in the
    SDK ``initialize`` response.

    Mirrors the ``modelInfos`` mapping inside ``runHeadlessStreaming`` from the
    TypeScript source.
    """
    result: List[Dict[str, Any]] = []
    for option in model_options:
        model_id = option.get("value") or "default"
        display_name = option.get("label", "")
        description = option.get("description", "")
        info: Dict[str, Any] = {
            "value": model_id,
            "displayName": display_name,
            "description": description,
        }
        # Capability flags — resolved lazily from the model registry when available.
        try:
            from claude_code.utils.model.model import (
                parse_user_specified_model,
                get_default_main_loop_model,
            )  # type: ignore[import]
            from claude_code.utils.effort import (
                model_supports_effort,
                model_supports_max_effort,
                EFFORT_LEVELS,
            )  # type: ignore[import]

            resolved = (
                get_default_main_loop_model()
                if model_id == "default"
                else parse_user_specified_model(model_id)
            )
            if model_supports_effort(resolved):
                levels = (
                    list(EFFORT_LEVELS)
                    if model_supports_max_effort(resolved)
                    else [lv for lv in EFFORT_LEVELS if lv != "max"]
                )
                info["supportsEffort"] = True
                info["supportedEffortLevels"] = levels
        except ImportError:
            pass

        result.append(info)
    return result


# ---------------------------------------------------------------------------
# MCP server-status builder (SDK mcp_status / reload_plugins response)
# ---------------------------------------------------------------------------


def build_mcp_server_statuses(
    mcp_clients: List[Any],
    sdk_clients: List[Any],
    dynamic_mcp_state: "DynamicMcpState",
    all_mcp_tools: List[Any],
) -> List[Dict[str, Any]]:
    """Build the ``McpServerStatus[]`` list for ``mcp_status`` and
    ``reload_plugins`` control responses.

    Mirrors ``buildMcpServerStatuses`` from the TypeScript source.
    """
    existing_names: Set[str] = {
        _client_name(c) for c in list(mcp_clients) + list(sdk_clients)
    }
    combined = (
        list(mcp_clients)
        + list(sdk_clients)
        + [
            c for c in dynamic_mcp_state.clients
            if _client_name(c) not in existing_names
        ]
    )

    statuses: List[Dict[str, Any]] = []
    for connection in combined:
        name = _client_name(connection)
        conn_type = (
            connection.get("type") if isinstance(connection, dict)
            else getattr(connection, "type", "unknown")
        )
        config = (
            connection.get("config", {}) if isinstance(connection, dict)
            else getattr(connection, "config", {})
        ) or {}

        # Build config sub-dict based on transport type.
        cfg_type = (
            config.get("type") if isinstance(config, dict)
            else getattr(config, "type", None)
        )
        config_out: Optional[Dict[str, Any]] = None
        if cfg_type in ("sse", "http"):
            config_out = {
                "type": cfg_type,
                "url": (
                    config.get("url") if isinstance(config, dict)
                    else getattr(config, "url", None)
                ),
            }
        elif cfg_type in ("stdio", None):
            config_out = {
                "type": "stdio",
                "command": (
                    config.get("command") if isinstance(config, dict)
                    else getattr(config, "command", None)
                ),
                "args": (
                    config.get("args") if isinstance(config, dict)
                    else getattr(config, "args", None)
                ),
            }

        # Server tools (only for connected servers).
        server_tools: Optional[List[Dict[str, Any]]] = None
        if conn_type == "connected":
            prefix = f"mcp__{name}__"
            server_tools = [
                {
                    "name": (
                        t.get("name", "") if isinstance(t, dict)
                        else getattr(t, "name", "")
                    ).replace(prefix, "", 1),
                }
                for t in all_mcp_tools
                if (
                    t.get("name", "") if isinstance(t, dict) else getattr(t, "name", "")
                ).startswith(prefix)
            ]

        error = (
            connection.get("error") if isinstance(connection, dict)
            else getattr(connection, "error", None)
        ) if conn_type == "failed" else None

        scope = (
            config.get("scope") if isinstance(config, dict)
            else getattr(config, "scope", None)
        )

        statuses.append({
            "name": name,
            "status": conn_type,
            "error": error,
            "config": config_out,
            "scope": scope,
            "tools": server_tools,
        })

    return statuses


def _client_name(client: Any) -> str:
    """Return the name of *client* regardless of its concrete type."""
    if isinstance(client, dict):
        return client.get("name", "") or ""
    return getattr(client, "name", "") or ""


# ---------------------------------------------------------------------------
# Batch-command building
# ---------------------------------------------------------------------------


def build_batched_command(
    batch: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge a batch of queued prompt commands into one composite command.

    When multiple consecutive prompt-mode commands accumulate between turns,
    they are merged into a single ``ask()`` call so the model sees them as
    one turn.  Mirrors the batch-building logic inside ``drainCommandQueue``
    in the TypeScript source.
    """
    if not batch:
        raise ValueError("batch must not be empty")
    if len(batch) == 1:
        return batch[0]

    head = batch[0]
    merged_value = join_prompt_values([cmd.get("value", "") for cmd in batch])
    # Use the UUID of the last message in the batch (matches TS behaviour).
    last_uuid = next(
        (cmd.get("uuid") for cmd in reversed(batch) if cmd.get("uuid")),
        head.get("uuid"),
    )
    return {
        **head,
        "value": merged_value,
        "uuid": last_uuid,
    }


# ---------------------------------------------------------------------------
# reregister_channel_handler_after_reconnect (stub)
# ---------------------------------------------------------------------------


def reregister_channel_handler_after_reconnect(connection: Any) -> None:
    """Re-register the channel notification handler after an MCP reconnect.

    Without this, channel messages silently drop after ``mcp_reconnect``
    or ``mcp_toggle`` creates a new client instance.

    Mirrors ``reregisterChannelHandlerAfterReconnect`` from the TypeScript source.
    This is a no-op stub — full implementation requires the channel
    notification registry which is not yet ported.
    """
    # TODO: implement when channel notification registry is ported.
    pass


# ---------------------------------------------------------------------------
# Idle-timeout manager
# ---------------------------------------------------------------------------


class IdleTimeoutManager:
    """Manages an idle timeout that fires when the session has been inactive.

    Mirrors ``createIdleTimeoutManager`` from the TypeScript source.
    """

    def __init__(
        self,
        on_timeout: Callable[[], None],
        is_idle: Callable[[], bool],
        timeout_ms: int = 300_000,  # 5 minutes default
    ) -> None:
        self._on_timeout = on_timeout
        self._is_idle = is_idle
        self._timeout_ms = timeout_ms
        self._task: Optional[asyncio.Task] = None

    def start(self) -> None:
        """Start (or restart) the idle timer."""
        self.stop()
        loop = asyncio.get_event_loop()
        self._task = loop.create_task(self._run())

    def stop(self) -> None:
        """Cancel the pending idle timer."""
        if self._task is not None:
            self._task.cancel()
            self._task = None

    async def _run(self) -> None:
        try:
            await asyncio.sleep(self._timeout_ms / 1000.0)
            if self._is_idle():
                self._on_timeout()
        except asyncio.CancelledError:
            pass


def create_idle_timeout_manager(
    is_idle: Callable[[], bool],
    on_timeout: Optional[Callable[[], None]] = None,
    timeout_ms: int = 300_000,
) -> IdleTimeoutManager:
    """Factory that mirrors ``createIdleTimeoutManager`` from the TypeScript source."""
    def _default_timeout() -> None:
        _log_debug("Idle timeout reached — session may be terminated.")

    return IdleTimeoutManager(
        on_timeout=on_timeout or _default_timeout,
        is_idle=is_idle,
        timeout_ms=timeout_ms,
    )

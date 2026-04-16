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
# runHeadless  (main entry-point stub)
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
    # NOTE: Full implementation requires the broader Claude Code Python runtime
    # (QueryEngine, StructuredIO, AppState, etc.) which are being ported in
    # parallel.  This stub validates the call signature and raises
    # NotImplementedError to surface missing dependencies rather than silently
    # doing nothing.
    raise NotImplementedError(
        "run_headless: full implementation pending completion of the "
        "Claude Code Python runtime (QueryEngine, StructuredIO, AppState)."
    )


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

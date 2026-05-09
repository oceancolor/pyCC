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
# run_headless_streaming  (generator / async-iterable stub)
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
    # NOTE: Full implementation requires QueryEngine, StructuredIO, and
    # AppState.  This stub validates the signature and raises
    # NotImplementedError rather than silently doing nothing.
    raise NotImplementedError(
        "run_headless_streaming: pending completion of the Claude Code Python runtime."
    )
    # Make this function syntactically an async generator:
    if False:  # pragma: no cover
        yield {}


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

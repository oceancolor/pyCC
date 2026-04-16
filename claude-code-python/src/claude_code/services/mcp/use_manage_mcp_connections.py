"""
MCP connection lifecycle manager. Ported from services/mcp/useManageMCPConnections.ts

Manages MCP (Model Context Protocol) server connections:
  - Connection lifecycle (connect, disconnect, reconnect)
  - Exponential-backoff automatic reconnection for non-stdio transports
  - get_active_connections()  — list live connections
  - connect_to_mcp_server()   — connect to a named server
  - disconnect_from_mcp_server() — cleanly disconnect
  - toggle_mcp_server()       — enable / disable a server
  - Connection-state monitoring and error handling

Design note:
  The TypeScript original is a React hook (useManageMCPConnections) that
  wires into component state.  In Python we expose a plain class
  MCPConnectionManager so callers can compose it however they like
  (singleton, injected dependency, etc.).
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reconnection constants
# ---------------------------------------------------------------------------

MAX_RECONNECT_ATTEMPTS = 5
INITIAL_BACKOFF_MS = 1_000
MAX_BACKOFF_MS = 30_000
MCP_BATCH_FLUSH_MS = 16  # ms window for coalescing state updates

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass
class ScopedMcpServerConfig:
    """Configuration for a single MCP server (mirrors ScopedMcpServerConfig in TS)."""

    name: str
    type: str = "stdio"  # 'stdio' | 'sse' | 'http' | 'ws' | 'sdk'
    scope: str = "project"  # 'project' | 'user' | 'enterprise' | 'dynamic' | 'claudeai'
    command: Optional[str] = None
    args: List[str] = field(default_factory=list)
    env: Dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    plugin_source: Optional[str] = None


@dataclass
class MCPServerConnection:
    """Runtime state of a single MCP server connection."""

    name: str
    config: ScopedMcpServerConfig
    # type mirrors the TS discriminated union:
    #   'pending' | 'connected' | 'failed' | 'disabled' | 'needs-auth'
    type: str = "pending"
    reconnect_attempt: int = 0
    max_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS
    tools: List[Any] = field(default_factory=list)
    commands: List[Any] = field(default_factory=list)
    resources: List[Any] = field(default_factory=list)
    capabilities: Optional[Dict[str, Any]] = None
    # Low-level client object (e.g. mcp SDK client); opaque to this layer.
    client: Optional[Any] = None
    error: Optional[str] = None


@dataclass
class ConnectionAttemptResult:
    """Result returned by a connection / reconnection attempt."""

    client: MCPServerConnection
    tools: List[Any] = field(default_factory=list)
    commands: List[Any] = field(default_factory=list)
    resources: List[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_transport_display_name(transport_type: str) -> str:
    """Return a human-readable name for a transport type."""
    if transport_type == "http":
        return "HTTP"
    if transport_type in ("ws", "ws-ide"):
        return "WebSocket"
    return "SSE"


def _is_remote_transport(transport_type: str) -> bool:
    """Return True for transports that support automatic reconnection."""
    return transport_type not in ("stdio", "sdk")


# ---------------------------------------------------------------------------
# MCPConnectionManager
# ---------------------------------------------------------------------------


class MCPConnectionManager:
    """
    Python equivalent of the useManageMCPConnections React hook.

    Usage::

        mgr = MCPConnectionManager(connect_fn, is_disabled_fn, set_enabled_fn)
        await mgr.connect_to_mcp_server(config)
        connections = mgr.get_active_connections()
        await mgr.disconnect_from_mcp_server("my-server")
    """

    def __init__(
        self,
        reconnect_impl: Optional[
            Callable[
                [str, ScopedMcpServerConfig],
                asyncio.coroutines,  # type: ignore[type-arg]
            ]
        ] = None,
        is_server_disabled: Optional[Callable[[str], bool]] = None,
        set_server_enabled: Optional[Callable[[str, bool], None]] = None,
    ) -> None:
        # Live connections keyed by server name
        self._connections: Dict[str, MCPServerConnection] = {}

        # Pending reconnect timers keyed by server name
        self._reconnect_tasks: Dict[str, asyncio.Task] = {}

        # Pending batched state-update callbacks
        self._pending_updates: List[MCPServerConnection] = []
        self._flush_task: Optional[asyncio.Task] = None

        # Injected callables (allow easy testing / mocking)
        self._reconnect_impl = reconnect_impl or self._default_reconnect_impl
        self._is_server_disabled = is_server_disabled or (lambda _: False)
        self._set_server_enabled = set_server_enabled or (lambda *_: None)

        # Optional callbacks fired after state changes (mirrors setAppState)
        self._on_state_change: Optional[Callable[[Dict[str, MCPServerConnection]], None]] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_state_change_callback(
        self,
        callback: Callable[[Dict[str, MCPServerConnection]], None],
    ) -> None:
        """Register a callback invoked whenever connection state changes."""
        self._on_state_change = callback

    def get_active_connections(self) -> List[MCPServerConnection]:
        """Return all connections that are currently in 'connected' state."""
        return [c for c in self._connections.values() if c.type == "connected"]

    def get_all_connections(self) -> List[MCPServerConnection]:
        """Return every known connection regardless of state."""
        return list(self._connections.values())

    def get_connection(self, server_name: str) -> Optional[MCPServerConnection]:
        """Look up a connection by server name."""
        return self._connections.get(server_name)

    async def connect_to_mcp_server(
        self,
        config: ScopedMcpServerConfig,
    ) -> MCPServerConnection:
        """
        Connect to an MCP server described by *config*.

        Sets the server to 'pending' while connecting, then updates to
        'connected' or 'failed' based on the result.
        Returns the final MCPServerConnection.
        """
        name = config.name
        conn = MCPServerConnection(name=name, config=config, type="pending")
        self._update_server(conn)

        try:
            result = await self._reconnect_impl(name, config)
            self._on_connection_attempt(result)
            return self._connections.get(name, conn)
        except Exception as exc:
            logger.error("[MCPConnectionManager] connect_to_mcp_server failed for %s: %s", name, exc)
            failed = MCPServerConnection(
                name=name,
                config=config,
                type="failed",
                error=str(exc),
            )
            self._update_server(failed)
            return failed

    async def disconnect_from_mcp_server(self, server_name: str) -> None:
        """
        Cleanly disconnect a server and cancel any pending reconnect timers.

        After this call the connection entry is removed from the manager.
        """
        self._cancel_reconnect_task(server_name)

        conn = self._connections.get(server_name)
        if conn and conn.type == "connected" and conn.client is not None:
            try:
                if hasattr(conn.client, "close"):
                    await conn.client.close()
                elif hasattr(conn.client, "aclose"):
                    await conn.client.aclose()
            except Exception as exc:
                logger.debug(
                    "[MCPConnectionManager] disconnect error for %s: %s",
                    server_name,
                    exc,
                )

        self._connections.pop(server_name, None)
        self._notify_state_change()

    async def reconnect_mcp_server(self, server_name: str) -> ConnectionAttemptResult:
        """
        Manually trigger a reconnect for *server_name*.

        Cancels any pending automatic retry first.
        Returns the connection attempt result (may still be 'failed').
        """
        conn = self._connections.get(server_name)
        if conn is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        self._cancel_reconnect_task(server_name)

        result = await self._reconnect_impl(server_name, conn.config)
        self._on_connection_attempt(result)
        return result

    async def toggle_mcp_server(self, server_name: str) -> None:
        """
        Toggle a server between enabled and disabled states.

        Mirrors toggleMcpServer in the TS hook:
          - disabled → mark pending → reconnect
          - enabled  → persist disabled → disconnect if connected
        """
        conn = self._connections.get(server_name)
        if conn is None:
            raise ValueError(f"MCP server '{server_name}' not found")

        is_currently_disabled = conn.type == "disabled"

        if not is_currently_disabled:
            # Disabling the server
            self._cancel_reconnect_task(server_name)
            self._set_server_enabled(server_name, False)

            if conn.type == "connected" and conn.client is not None:
                try:
                    if hasattr(conn.client, "close"):
                        await conn.client.close()
                except Exception:
                    pass

            self._update_server(
                MCPServerConnection(
                    name=server_name,
                    config=conn.config,
                    type="disabled",
                    tools=[],
                    commands=[],
                    resources=[],
                )
            )
        else:
            # Re-enabling the server
            self._set_server_enabled(server_name, True)
            self._update_server(
                MCPServerConnection(
                    name=server_name,
                    config=conn.config,
                    type="pending",
                )
            )
            result = await self._reconnect_impl(server_name, conn.config)
            self._on_connection_attempt(result)

    async def initialize_servers(
        self,
        configs: Dict[str, ScopedMcpServerConfig],
    ) -> None:
        """
        Add all servers from *configs* to the connection map as 'pending'
        (or 'disabled' if they are currently disabled).

        Servers that already exist in the manager are skipped.
        This mirrors the initializeServersAsPending() effect in the TS hook.
        """
        existing_names = set(self._connections)
        new_conns = []
        for name, config in configs.items():
            if name in existing_names:
                continue
            state = "disabled" if self._is_server_disabled(name) else "pending"
            new_conns.append(MCPServerConnection(name=name, config=config, type=state))

        for conn in new_conns:
            self._connections[conn.name] = conn

        if new_conns:
            self._notify_state_change()

    async def connect_all(
        self,
        configs: Dict[str, ScopedMcpServerConfig],
        *,
        concurrent: bool = True,
    ) -> List[MCPServerConnection]:
        """
        Connect to all servers in *configs*, skipping disabled ones.

        Args:
            configs: Mapping of server-name → config.
            concurrent: If True, connect to all servers concurrently.

        Returns:
            List of resulting MCPServerConnection objects.
        """
        enabled = {
            name: cfg
            for name, cfg in configs.items()
            if not self._is_server_disabled(name)
        }

        if concurrent:
            results = await asyncio.gather(
                *[self.connect_to_mcp_server(cfg) for cfg in enabled.values()],
                return_exceptions=True,
            )
            conns = []
            for name, res in zip(enabled, results):
                if isinstance(res, BaseException):
                    logger.error(
                        "[MCPConnectionManager] connect_all failed for %s: %s",
                        name,
                        res,
                    )
                    conns.append(
                        MCPServerConnection(
                            name=name,
                            config=enabled[name],
                            type="failed",
                            error=str(res),
                        )
                    )
                else:
                    conns.append(res)  # type: ignore[arg-type]
            return conns
        else:
            conns = []
            for cfg in enabled.values():
                conns.append(await self.connect_to_mcp_server(cfg))
            return conns

    def cleanup(self) -> None:
        """Cancel all pending reconnect tasks and flush timers (call on shutdown)."""
        for task in list(self._reconnect_tasks.values()):
            task.cancel()
        self._reconnect_tasks.clear()

        if self._flush_task is not None:
            self._flush_task.cancel()
            self._flush_task = None

        # Flush any remaining pending updates synchronously
        self._do_flush()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _on_connection_attempt(self, result: ConnectionAttemptResult) -> None:
        """
        Process the result of a connection attempt.
        Registers notification handlers, sets up auto-reconnect on close, etc.
        """
        client_conn = result.client
        conn = MCPServerConnection(
            name=client_conn.name,
            config=client_conn.config,
            type=client_conn.type,
            tools=result.tools,
            commands=result.commands,
            resources=result.resources,
            capabilities=client_conn.capabilities,
            client=client_conn.client,
            error=client_conn.error,
        )
        self._update_server(conn)

        if conn.type == "connected" and conn.client is not None:
            self._setup_reconnect_on_close(conn)

    def _setup_reconnect_on_close(self, conn: MCPServerConnection) -> None:
        """
        Set an on-close handler on the low-level client that triggers
        automatic reconnection for remote (non-stdio/sdk) transports.
        """
        config_type = conn.config.type or "stdio"

        def _on_close() -> None:
            if self._is_server_disabled(conn.name):
                logger.debug(
                    "[MCPConnectionManager] %s: server disabled, skip reconnect",
                    conn.name,
                )
                return

            if not _is_remote_transport(config_type):
                # stdio / sdk connections are not auto-reconnected
                updated = MCPServerConnection(
                    name=conn.name,
                    config=conn.config,
                    type="failed",
                    tools=[],
                    commands=[],
                    resources=[],
                )
                self._update_server(updated)
                return

            transport_name = _get_transport_display_name(config_type)
            logger.debug(
                "[MCPConnectionManager] %s: %s closed, scheduling reconnect",
                conn.name,
                transport_name,
            )
            self._cancel_reconnect_task(conn.name)
            task = asyncio.ensure_future(
                self._reconnect_with_backoff(conn, config_type)
            )
            self._reconnect_tasks[conn.name] = task

        # Wire the callback into the SDK client if it exposes an onclose slot
        if conn.client is not None and hasattr(conn.client, "onclose"):
            conn.client.onclose = _on_close

    async def _reconnect_with_backoff(
        self,
        original_conn: MCPServerConnection,
        config_type: str,
    ) -> None:
        """
        Attempt to reconnect to a server using exponential back-off.
        Mirrors reconnectWithBackoff() closure in the TS hook.
        """
        transport_name = _get_transport_display_name(config_type)
        server_name = original_conn.name

        for attempt in range(1, MAX_RECONNECT_ATTEMPTS + 1):
            if self._is_server_disabled(server_name):
                logger.debug(
                    "[MCPConnectionManager] %s: disabled during reconnect, stopping",
                    server_name,
                )
                self._reconnect_tasks.pop(server_name, None)
                return

            # Mark as pending / reconnecting
            pending_conn = MCPServerConnection(
                name=server_name,
                config=original_conn.config,
                type="pending",
                reconnect_attempt=attempt,
                max_reconnect_attempts=MAX_RECONNECT_ATTEMPTS,
            )
            self._update_server(pending_conn)

            start = time.monotonic()
            try:
                result = await self._reconnect_impl(server_name, original_conn.config)
                elapsed = int((time.monotonic() - start) * 1000)

                if result.client.type == "connected":
                    logger.debug(
                        "[MCPConnectionManager] %s: %s reconnect succeeded in %dms (attempt %d)",
                        server_name,
                        transport_name,
                        elapsed,
                        attempt,
                    )
                    self._reconnect_tasks.pop(server_name, None)
                    self._on_connection_attempt(result)
                    return

                logger.debug(
                    "[MCPConnectionManager] %s: reconnect attempt %d → status=%s",
                    server_name,
                    attempt,
                    result.client.type,
                )

                if attempt == MAX_RECONNECT_ATTEMPTS:
                    self._reconnect_tasks.pop(server_name, None)
                    self._on_connection_attempt(result)
                    return

            except Exception as exc:
                elapsed = int((time.monotonic() - start) * 1000)
                logger.error(
                    "[MCPConnectionManager] %s: reconnect attempt %d failed in %dms: %s",
                    server_name,
                    attempt,
                    elapsed,
                    exc,
                )
                if attempt == MAX_RECONNECT_ATTEMPTS:
                    self._reconnect_tasks.pop(server_name, None)
                    failed = MCPServerConnection(
                        name=server_name,
                        config=original_conn.config,
                        type="failed",
                        error=str(exc),
                    )
                    self._update_server(failed)
                    return

            # Exponential back-off before next attempt
            backoff_ms = min(
                INITIAL_BACKOFF_MS * (2 ** (attempt - 1)),
                MAX_BACKOFF_MS,
            )
            logger.debug(
                "[MCPConnectionManager] %s: scheduling attempt %d in %dms",
                server_name,
                attempt + 1,
                backoff_ms,
            )
            try:
                await asyncio.sleep(backoff_ms / 1000.0)
            except asyncio.CancelledError:
                logger.debug(
                    "[MCPConnectionManager] %s: reconnect task cancelled", server_name
                )
                return

    def _update_server(self, conn: MCPServerConnection) -> None:
        """
        Queue a server state update.
        Updates are batched and flushed within MCP_BATCH_FLUSH_MS to coalesce
        multiple rapid updates (mirrors the batched setAppState in the TS hook).
        """
        self._pending_updates.append(conn)
        if self._flush_task is None or self._flush_task.done():
            loop = asyncio.get_event_loop()
            if loop.is_running():
                self._flush_task = loop.call_later(  # type: ignore[assignment]
                    MCP_BATCH_FLUSH_MS / 1000.0,
                    self._do_flush,
                )
            else:
                self._do_flush()

    def _do_flush(self) -> None:
        """Apply all pending state updates in a single pass."""
        updates = self._pending_updates[:]
        self._pending_updates.clear()

        for conn in updates:
            existing = self._connections.get(conn.name)
            if existing is None:
                self._connections[conn.name] = conn
            else:
                # Merge: keep tools/commands/resources if the update leaves them empty
                # and the existing state has them (mirrors TS undefined-preservation logic)
                merged_tools = conn.tools if conn.tools else existing.tools
                merged_commands = conn.commands if conn.commands else existing.commands
                merged_resources = conn.resources if conn.resources else existing.resources

                if conn.type in ("disabled", "failed"):
                    # Explicit clear for disabled/failed
                    merged_tools = conn.tools
                    merged_commands = conn.commands
                    merged_resources = conn.resources

                self._connections[conn.name] = MCPServerConnection(
                    name=conn.name,
                    config=conn.config,
                    type=conn.type,
                    reconnect_attempt=conn.reconnect_attempt,
                    max_reconnect_attempts=conn.max_reconnect_attempts,
                    tools=merged_tools,
                    commands=merged_commands,
                    resources=merged_resources,
                    capabilities=conn.capabilities or existing.capabilities,
                    client=conn.client or existing.client,
                    error=conn.error,
                )

        if updates:
            self._notify_state_change()

    def _cancel_reconnect_task(self, server_name: str) -> None:
        """Cancel any pending reconnect asyncio.Task for *server_name*."""
        task = self._reconnect_tasks.pop(server_name, None)
        if task is not None and not task.done():
            task.cancel()

    def _notify_state_change(self) -> None:
        """Invoke the state-change callback if registered."""
        if self._on_state_change is not None:
            try:
                self._on_state_change(dict(self._connections))
            except Exception as exc:
                logger.debug("[MCPConnectionManager] state-change callback error: %s", exc)

    # ------------------------------------------------------------------
    # Default reconnect implementation (no-op stub)
    # ------------------------------------------------------------------

    @staticmethod
    async def _default_reconnect_impl(
        server_name: str,
        config: ScopedMcpServerConfig,
    ) -> ConnectionAttemptResult:
        """
        Default reconnect implementation used when none is injected.
        Real code should inject the reconnect_mcp_server_impl from client.py.
        """
        logger.debug(
            "[MCPConnectionManager] _default_reconnect_impl called for %s "
            "(no real implementation injected)",
            server_name,
        )
        return ConnectionAttemptResult(
            client=MCPServerConnection(
                name=server_name,
                config=config,
                type="failed",
                error="No reconnect implementation provided",
            )
        )


# ---------------------------------------------------------------------------
# Module-level convenience factory
# ---------------------------------------------------------------------------


def create_mcp_connection_manager(
    reconnect_impl: Optional[Callable] = None,
    is_server_disabled: Optional[Callable[[str], bool]] = None,
    set_server_enabled: Optional[Callable[[str, bool], None]] = None,
) -> MCPConnectionManager:
    """
    Factory function that wires up an MCPConnectionManager with the
    production implementations from client.py and config.py (when available).

    Falls back to no-op stubs if the dependencies are not importable.
    """
    if reconnect_impl is None:
        try:
            from claude_code.services.mcp.client import reconnect_mcp_server_impl  # type: ignore
            reconnect_impl = reconnect_mcp_server_impl
        except ImportError:
            pass

    if is_server_disabled is None:
        try:
            from claude_code.services.mcp.config import is_mcp_server_disabled  # type: ignore
            is_server_disabled = is_mcp_server_disabled
        except ImportError:
            pass

    if set_server_enabled is None:
        try:
            from claude_code.services.mcp.config import set_mcp_server_enabled  # type: ignore
            set_server_enabled = set_mcp_server_enabled
        except ImportError:
            pass

    return MCPConnectionManager(
        reconnect_impl=reconnect_impl,
        is_server_disabled=is_server_disabled,
        set_server_enabled=set_server_enabled,
    )


# ---------------------------------------------------------------------------
# Module-level convenience functions (mirrors individual TS export names)
# ---------------------------------------------------------------------------


async def get_active_connections(
    manager: Optional[MCPConnectionManager] = None,
) -> List[MCPServerConnection]:
    """
    Return the list of currently connected MCP servers from *manager*.
    If manager is None, a fresh (empty) manager is used.
    """
    if manager is None:
        manager = create_mcp_connection_manager()
    return manager.get_active_connections()


async def connect_to_mcp_server(
    config: ScopedMcpServerConfig,
    manager: Optional[MCPConnectionManager] = None,
) -> MCPServerConnection:
    """Connect to a single MCP server. Creates a throw-away manager if none given."""
    if manager is None:
        manager = create_mcp_connection_manager()
    return await manager.connect_to_mcp_server(config)


async def disconnect_from_mcp_server(
    server_name: str,
    manager: MCPConnectionManager,
) -> None:
    """Disconnect from *server_name* using *manager*."""
    await manager.disconnect_from_mcp_server(server_name)

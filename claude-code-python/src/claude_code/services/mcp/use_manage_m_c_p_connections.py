"""
MCP connection manager.
Ported from services/mcp/useManageMCPConnections.ts (1141 lines)

Manages the lifecycle of MCP (Model Context Protocol) server connections:
connecting, disconnecting, monitoring, and restarting servers.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class MCPConnectionStatus(str, Enum):
    """Connection status for an MCP server."""
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    RESTARTING = "restarting"


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""
    name: str
    command: Optional[str] = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: Optional[str] = None  # For HTTP/SSE transports
    transport: str = "stdio"  # "stdio" | "sse" | "http"
    timeout_ms: int = 30_000
    restart_on_failure: bool = True
    max_restart_attempts: int = 3


@dataclass
class MCPConnection:
    """Represents an active MCP server connection."""
    config: MCPServerConfig
    status: MCPConnectionStatus = MCPConnectionStatus.DISCONNECTED
    tools: list[dict] = field(default_factory=list)
    resources: list[dict] = field(default_factory=list)
    prompts: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    restart_count: int = 0
    _client: Any = field(default=None, repr=False)

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def is_connected(self) -> bool:
        return self.status == MCPConnectionStatus.CONNECTED


ConnectionChangeCallback = Callable[[str, MCPConnectionStatus], None]


class MCPConnectionManager:
    """
    Manages MCP server connections.

    Handles connecting to servers, tracking their state, providing
    their capabilities (tools/resources/prompts), and restarting
    failed connections.
    """

    def __init__(self) -> None:
        self._connections: dict[str, MCPConnection] = {}
        self._change_callbacks: list[ConnectionChangeCallback] = []
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def on_connection_change(self, callback: ConnectionChangeCallback) -> Callable:
        """Register a callback for connection status changes. Returns unsubscribe fn."""
        self._change_callbacks.append(callback)

        def unsubscribe() -> None:
            try:
                self._change_callbacks.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def _notify_change(self, name: str, status: MCPConnectionStatus) -> None:
        for cb in list(self._change_callbacks):
            try:
                cb(name, status)
            except Exception as exc:
                logger.debug("Connection change callback error: %s", exc)

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    async def connect(self, config: MCPServerConfig) -> MCPConnection:
        """
        Connect to an MCP server described by *config*.

        Returns the MCPConnection object. If a connection with the same
        name already exists, it is returned as-is (no duplicate).
        """
        async with self._lock:
            if config.name in self._connections:
                return self._connections[config.name]

            conn = MCPConnection(config=config, status=MCPConnectionStatus.CONNECTING)
            self._connections[config.name] = conn

        self._notify_change(config.name, MCPConnectionStatus.CONNECTING)

        try:
            await self._do_connect(conn)
            conn.status = MCPConnectionStatus.CONNECTED
            self._notify_change(config.name, MCPConnectionStatus.CONNECTED)
            logger.debug("MCP server '%s' connected", config.name)
        except Exception as exc:
            conn.status = MCPConnectionStatus.ERROR
            conn.error = str(exc)
            self._notify_change(config.name, MCPConnectionStatus.ERROR)
            logger.warning("MCP server '%s' connection failed: %s", config.name, exc)
            if config.restart_on_failure:
                asyncio.create_task(self._schedule_restart(conn))

        return conn

    async def _do_connect(self, conn: MCPConnection) -> None:
        """
        Perform the actual connection to the MCP server.
        Stub: real implementation would launch subprocess / open SSE.
        """
        # Placeholder — real implementation would:
        #   1. Launch subprocess (stdio transport) or open WebSocket/HTTP
        #   2. Perform MCP initialize handshake
        #   3. List tools, resources, prompts
        #   4. Store client in conn._client
        logger.debug(
            "Connecting to MCP server '%s' (transport=%s)",
            conn.name,
            conn.config.transport,
        )
        # Simulate async I/O
        await asyncio.sleep(0)
        conn.tools = []
        conn.resources = []
        conn.prompts = []

    async def disconnect(self, name: str) -> None:
        """Disconnect from an MCP server."""
        async with self._lock:
            conn = self._connections.pop(name, None)

        if conn is None:
            return

        conn.status = MCPConnectionStatus.DISCONNECTED
        try:
            await self._do_disconnect(conn)
        except Exception as exc:
            logger.debug("Error disconnecting '%s': %s", name, exc)
        self._notify_change(name, MCPConnectionStatus.DISCONNECTED)
        logger.debug("MCP server '%s' disconnected", name)

    async def _do_disconnect(self, conn: MCPConnection) -> None:
        """Close the underlying transport. Stub."""
        await asyncio.sleep(0)

    async def disconnect_all(self) -> None:
        """Disconnect all active connections."""
        names = list(self._connections.keys())
        await asyncio.gather(*(self.disconnect(n) for n in names), return_exceptions=True)

    # ------------------------------------------------------------------
    # Restart
    # ------------------------------------------------------------------

    async def _schedule_restart(
        self,
        conn: MCPConnection,
        delay_s: float = 5.0,
    ) -> None:
        """Wait *delay_s* seconds then reconnect, up to max_restart_attempts."""
        if conn.restart_count >= conn.config.max_restart_attempts:
            logger.warning(
                "MCP server '%s' exceeded max restart attempts (%d)",
                conn.name,
                conn.config.max_restart_attempts,
            )
            return

        conn.restart_count += 1
        conn.status = MCPConnectionStatus.RESTARTING
        self._notify_change(conn.name, MCPConnectionStatus.RESTARTING)

        logger.debug(
            "MCP server '%s' restarting in %.1fs (attempt %d/%d)",
            conn.name,
            delay_s,
            conn.restart_count,
            conn.config.max_restart_attempts,
        )
        await asyncio.sleep(delay_s)

        # Re-add to tracking dict and attempt connection
        async with self._lock:
            self._connections[conn.name] = conn
        await self._do_connect(conn)
        if conn.status != MCPConnectionStatus.ERROR:
            conn.status = MCPConnectionStatus.CONNECTED
            self._notify_change(conn.name, MCPConnectionStatus.CONNECTED)

    async def restart(self, name: str) -> Optional[MCPConnection]:
        """Manually restart a named connection."""
        conn = self._connections.get(name)
        if conn is None:
            return None
        await self._do_disconnect(conn)
        conn.restart_count = 0  # Manual restart resets counter
        await self._schedule_restart(conn, delay_s=0)
        return conn

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_connection(self, name: str) -> Optional[MCPConnection]:
        """Return the connection object for a server, or None."""
        return self._connections.get(name)

    def get_all_connections(self) -> list[MCPConnection]:
        """Return all tracked connections."""
        return list(self._connections.values())

    def get_connected(self) -> list[MCPConnection]:
        """Return only successfully connected servers."""
        return [c for c in self._connections.values() if c.is_connected]

    def get_all_tools(self) -> list[dict]:
        """Aggregate tools from all connected servers."""
        tools: list[dict] = []
        for conn in self.get_connected():
            for tool in conn.tools:
                tools.append({**tool, "_server": conn.name})
        return tools

    def get_all_resources(self) -> list[dict]:
        """Aggregate resources from all connected servers."""
        resources: list[dict] = []
        for conn in self.get_connected():
            for res in conn.resources:
                resources.append({**res, "_server": conn.name})
        return resources

    def get_all_prompts(self) -> list[dict]:
        """Aggregate prompts from all connected servers."""
        prompts: list[dict] = []
        for conn in self.get_connected():
            for prompt in conn.prompts:
                prompts.append({**prompt, "_server": conn.name})
        return prompts


# ---------------------------------------------------------------------------
# Module-level singleton helpers
# ---------------------------------------------------------------------------

_manager: Optional[MCPConnectionManager] = None


def get_connection_manager() -> MCPConnectionManager:
    """Return the module-level MCPConnectionManager singleton."""
    global _manager
    if _manager is None:
        _manager = MCPConnectionManager()
    return _manager


async def connect_server(config: MCPServerConfig) -> MCPConnection:
    """Connect a server using the global manager."""
    return await get_connection_manager().connect(config)


async def disconnect_server(name: str) -> None:
    """Disconnect a server using the global manager."""
    await get_connection_manager().disconnect(name)


def get_all_mcp_tools() -> list[dict]:
    """Get all tools from all connected MCP servers."""
    return get_connection_manager().get_all_tools()

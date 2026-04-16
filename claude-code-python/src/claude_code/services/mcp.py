# 原始 TS: services/mcp/client.ts + MCPConnectionManager.tsx
"""MCP (Model Context Protocol) service stub.

Manages connections to local/remote MCP servers and exposes their tools,
prompts, and resources to the agent loop.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any

logger = logging.getLogger(__name__)


class MCPTransportType(Enum):
    STDIO = auto()
    SSE = auto()
    STREAMABLE_HTTP = auto()


@dataclass
class MCPServerConfig:
    """Configuration for a single MCP server."""

    name: str
    transport: MCPTransportType = MCPTransportType.STDIO
    # stdio transport
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    # network transports
    url: str = ""
    # auth
    oauth_client_id: str = ""


@dataclass
class MCPTool:
    """A tool exposed by an MCP server."""

    name: str
    description: str
    input_schema: dict[str, Any]
    server_name: str


@dataclass
class MCPServerConnection:
    """Runtime state for a connected MCP server."""

    config: MCPServerConfig
    tools: list[MCPTool] = field(default_factory=list)
    connected: bool = False
    error: str | None = None


class MCPConnectionManager:
    """Manages the lifecycle of all MCP server connections.

    TODO: Implement actual stdio/SSE/HTTP transports using the
          modelcontextprotocol Python SDK (mcp package).
    """

    def __init__(self) -> None:
        self._connections: dict[str, MCPServerConnection] = {}
        self._lock = asyncio.Lock()

    async def connect(self, config: MCPServerConfig) -> MCPServerConnection:
        """Connect to an MCP server and retrieve its tool list."""
        async with self._lock:
            conn = MCPServerConnection(config=config)
            # TODO: establish transport, call tools/list
            conn.connected = True
            self._connections[config.name] = conn
            logger.info("MCP server '%s' connected (stub)", config.name)
            return conn

    async def disconnect(self, name: str) -> None:
        """Disconnect a server by name."""
        async with self._lock:
            conn = self._connections.pop(name, None)
            if conn:
                conn.connected = False
                logger.info("MCP server '%s' disconnected", name)

    async def call_tool(
        self,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any],
    ) -> Any:
        """Call a tool on a connected MCP server.

        TODO: Route to real transport.
        """
        conn = self._connections.get(server_name)
        if conn is None:
            raise ValueError(f"MCP server '{server_name}' not connected")
        logger.debug("MCP call_tool %s::%s", server_name, tool_name)
        # TODO: implement real call
        return {"result": "stub", "server": server_name, "tool": tool_name}

    def get_all_tools(self) -> list[MCPTool]:
        """Return tools from all connected servers."""
        tools: list[MCPTool] = []
        for conn in self._connections.values():
            tools.extend(conn.tools)
        return tools

    @property
    def connections(self) -> dict[str, MCPServerConnection]:
        return dict(self._connections)


# Module-level singleton
_manager: MCPConnectionManager | None = None


def get_mcp_manager() -> MCPConnectionManager:
    global _manager  # noqa: PLW0603
    if _manager is None:
        _manager = MCPConnectionManager()
    return _manager


async def call_ide_rpc(method: str, params: dict[str, Any] | None = None) -> Any:
    """Call the IDE MCP server (used for diagnostics, file ops, etc.).

    TODO: Resolve IDE server name from config and forward via manager.
    """
    logger.debug("call_ide_rpc: %s %s (stub)", method, params)
    return None

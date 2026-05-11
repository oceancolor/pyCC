"""McpAuthTool — pseudo-tool for unauthenticated MCP servers.
Ported from McpAuthTool/McpAuthTool.ts.
"""
from __future__ import annotations
from typing import Any, Dict, Literal, Optional, TypedDict

MCP_AUTH_TOOL_NAME_SUFFIX = "authenticate"


class McpAuthOutput(TypedDict):
    status: Literal["auth_url", "unsupported", "error"]
    message: str
    auth_url: Optional[str]


def build_mcp_tool_name(server_name: str, tool_name: str) -> str:
    """Construct the canonical MCP tool name."""
    return f"mcp__{server_name}__{tool_name}"


class McpAuthTool:
    """Pseudo-tool for an MCP server that is installed but not yet authenticated.

    When called, starts an OAuth flow and returns an authorization URL.
    Ported from McpAuthTool/McpAuthTool.ts — the TypeScript original
    is a factory function; here we model it as a class with a server-specific
    constructor.
    """

    def __init__(self, server_name: str, config: Dict[str, Any]) -> None:
        self.server_name = server_name
        self.config = config
        transport = config.get("type", "stdio")
        url = config.get("url", "")
        location = f"{transport} at {url}" if url else transport

        self.name = build_mcp_tool_name(server_name, MCP_AUTH_TOOL_NAME_SUFFIX)
        self.description = (
            f"The `{server_name}` MCP server ({location}) is installed but requires "
            "authentication. Call this tool to start the OAuth flow — you'll receive an "
            "authorization URL to share with the user. Once the user completes authorization "
            "in their browser, the server's real tools will become available automatically."
        )
        self.is_mcp = True
        self.mcp_info = {"server_name": server_name, "tool_name": MCP_AUTH_TOOL_NAME_SUFFIX}
        self.max_result_size_chars = 10_000
        self.is_read_only = False
        self.is_concurrency_safe = False

    async def call(self, _input: Dict[str, Any] = {}, context: Any = None) -> Dict[str, Any]:
        """Initiate OAuth flow for this MCP server."""
        transport = self.config.get("type", "stdio")

        # claude.ai connectors use a separate auth flow
        if transport == "claudeai-proxy":
            return {
                "data": {
                    "status": "unsupported",
                    "message": (
                        f'This is a claude.ai MCP connector. Ask the user to run /mcp '
                        f'and select "{self.server_name}" to authenticate.'
                    ),
                    "auth_url": None,
                }
            }

        # OAuth is only supported for SSE and HTTP transports
        if transport not in ("sse", "http"):
            return {
                "data": {
                    "status": "unsupported",
                    "message": (
                        f'Server "{self.server_name}" uses {transport} transport which does '
                        "not support OAuth from this tool. Ask the user to run /mcp and "
                        "authenticate manually."
                    ),
                    "auth_url": None,
                }
            }

        # In the Python port we cannot drive a real browser-based OAuth flow
        # without additional infrastructure. Return an informative stub.
        url = self.config.get("url", "")
        return {
            "data": {
                "status": "unsupported",
                "message": (
                    f"OAuth flow for {self.server_name} is not yet implemented in the "
                    f"Python port. Please authenticate manually at: {url or '(unknown URL)'}"
                ),
                "auth_url": None,
            }
        }

    def map_tool_result(self, data: Dict[str, Any], tool_use_id: str) -> Dict[str, Any]:
        inner = data.get("data", data)
        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": inner.get("message", ""),
        }


def create_mcp_auth_tool(server_name: str, config: Dict[str, Any]) -> McpAuthTool:
    """Factory function mirroring the TypeScript createMcpAuthTool."""
    return McpAuthTool(server_name, config)

"""
Entrypoints package for Claude Code.

Provides public-facing APIs:
- agent_sdk_types: Re-exports all SDK types and function stubs
- init: Application initialization
- mcp: MCP server entrypoint
- sandbox_types: Sandbox configuration types
- sdk/: Serializable SDK schemas and types
"""

from claude_code.entrypoints.agent_sdk_types import (
    AbortError,
    query,
    list_sessions,
    get_session_info,
    get_session_messages,
    rename_session,
    tag_session,
    fork_session,
)
from claude_code.entrypoints.init import (
    init,
    initialize_telemetry_after_trust,
    ConfigParseError,
)
from claude_code.entrypoints.sandbox_types import (
    SandboxSettings,
    SandboxNetworkConfig,
    SandboxFilesystemConfig,
)

__all__ = [
    # agent SDK
    "AbortError",
    "query",
    "list_sessions",
    "get_session_info",
    "get_session_messages",
    "rename_session",
    "tag_session",
    "fork_session",
    # init
    "init",
    "initialize_telemetry_after_trust",
    "ConfigParseError",
    # sandbox
    "SandboxSettings",
    "SandboxNetworkConfig",
    "SandboxFilesystemConfig",
]

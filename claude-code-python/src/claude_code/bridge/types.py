# 原始 TS: bridge/types.ts
"""
Bridge 协议类型定义。

Bridge 是 Claude Code 连接远程 claude.ai 环境的通道，
提供远程控制 (Remote Control) 功能。
"""

from __future__ import annotations

from typing import Any, Literal
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_SESSION_TIMEOUT_MS: int = 24 * 60 * 60 * 1000  # 24 hours in ms

BRIDGE_LOGIN_INSTRUCTION: str = (
    "Remote Control is only available with claude.ai subscriptions. "
    "Please use `/login` to sign in with your claude.ai account."
)

BRIDGE_LOGIN_ERROR: str = (
    "Error: You must be logged in to use Remote Control.\n\n"
    + BRIDGE_LOGIN_INSTRUCTION
)

REMOTE_CONTROL_DISCONNECTED_MSG: str = "Remote Control disconnected."


# ---------------------------------------------------------------------------
# Protocol types — Environments API
# ---------------------------------------------------------------------------

@dataclass
class WorkData:
    """Payload embedded in a WorkResponse."""
    type: Literal["session", "healthcheck"]
    id: str


@dataclass
class WorkResponse:
    """A unit of work dispatched from the bridge server."""
    id: str
    type: Literal["work"]
    environment_id: str
    state: str
    data: WorkData
    secret: str          # base64url-encoded JSON (WorkSecret)
    created_at: str


@dataclass
class WorkSecretSource:
    type: str
    git_info: dict[str, Any] | None = None


@dataclass
class WorkSecretAuth:
    type: str
    token: str


@dataclass
class WorkSecret:
    """Decoded contents of WorkResponse.secret."""
    version: int
    session_ingress_token: str
    api_base_url: str
    sources: list[WorkSecretSource] = field(default_factory=list)
    auth: list[WorkSecretAuth] = field(default_factory=list)
    claude_code_args: dict[str, str] | None = None
    mcp_config: Any | None = None
    environment_variables: dict[str, str] | None = None
    use_code_sessions: bool | None = None


@dataclass
class PermissionResponseEvent:
    """Event sent back to the bridge after a permission prompt."""
    type: Literal["permission_response"]
    decision: Literal["allow", "deny"]
    tool_name: str
    tool_use_id: str


# ---------------------------------------------------------------------------
# Bridge client interface (protocol)
# ---------------------------------------------------------------------------

class BridgeConfig:
    """Runtime configuration for a bridge connection."""

    def __init__(
        self,
        base_url: str,
        access_token: str | None = None,
        runner_version: str = "unknown",
    ) -> None:
        self.base_url = base_url
        self.access_token = access_token
        self.runner_version = runner_version


class BridgeApiClient:
    """Abstract interface for bridge API operations."""

    def get_work(self, environment_id: str) -> WorkResponse | None:
        """Poll for the next unit of work. Returns None if none available."""
        # TODO: implement HTTP polling
        raise NotImplementedError

    def complete_work(self, work_id: str, result: dict[str, Any]) -> None:
        """Mark a work item as complete."""
        # TODO: implement HTTP completion
        raise NotImplementedError

    def respond_to_permission(self, event: PermissionResponseEvent) -> None:
        """Send a permission response back to the bridge."""
        # TODO: implement permission response
        raise NotImplementedError

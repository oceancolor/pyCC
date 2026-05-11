"""
Channel notifications for MCP servers.
Ported from services/mcp/channelNotification.ts

Lets an MCP server push user messages into the conversation. A "channel"
(Discord, Slack, SMS, etc.) is just an MCP server that:
  - exposes tools for outbound messages (e.g. `send_message`) — standard MCP
  - sends `notifications/claude/channel` notifications for inbound — this file

The notification handler wraps the content in a <channel> tag and enqueues it.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

# XML attribute key validation — only plain identifiers are accepted
SAFE_META_KEY = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")

CHANNEL_TAG = "channel"

CHANNEL_PERMISSION_METHOD = "notifications/claude/channel/permission"
CHANNEL_MESSAGE_METHOD = "notifications/claude/channel"


# ---------------------------------------------------------------------------
# Schema / data types
# ---------------------------------------------------------------------------

@dataclass
class ChannelMessageNotification:
    """Inbound channel message from an MCP server."""
    method: str  # "notifications/claude/channel"
    content: str
    meta: dict[str, str] = field(default_factory=dict)


@dataclass
class ChannelPermissionNotification:
    """Structured permission reply from a channel server."""
    method: str  # "notifications/claude/channel/permission"
    request_id: str
    behavior: str  # "allow" | "deny"


@dataclass
class ChannelPermissionRequestParams:
    """Outbound: CC → server, when a permission dialog opens."""
    request_id: str
    tool_name: str
    description: str
    input_preview: str  # JSON-stringified tool input, truncated to 200 chars


class ChannelGateKind(str, Enum):
    CAPABILITY = "capability"
    DISABLED = "disabled"
    AUTH = "auth"
    POLICY = "policy"
    SESSION = "session"
    MARKETPLACE = "marketplace"
    ALLOWLIST = "allowlist"


@dataclass
class ChannelGateResult:
    action: str  # "register" | "skip"
    kind: Optional[ChannelGateKind] = None
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# XML wrapping
# ---------------------------------------------------------------------------

def _escape_xml_attr(value: str) -> str:
    """Escape a string for use as an XML attribute value."""
    return (
        value
        .replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def wrap_channel_message(
    server_name: str,
    content: str,
    meta: Optional[dict[str, str]] = None,
) -> str:
    """
    Wrap a channel message in a <channel> XML tag.

    Meta keys become XML attribute names — only plain identifiers are accepted
    to prevent injection via crafted keys.
    """
    attrs = ""
    if meta:
        for key, value in meta.items():
            if SAFE_META_KEY.match(key):
                attrs += f' {key}="{_escape_xml_attr(value)}"'
    return (
        f'<{CHANNEL_TAG} source="{_escape_xml_attr(server_name)}"{attrs}>\n'
        f"{content}\n"
        f"</{CHANNEL_TAG}>"
    )


# ---------------------------------------------------------------------------
# Notification dispatch
# ---------------------------------------------------------------------------

_notification_handlers: list[Callable] = []


def register_notification_handler(handler: Callable) -> None:
    """Register a handler for incoming channel notifications."""
    _notification_handlers.append(handler)


def unregister_notification_handler(handler: Callable) -> None:
    """Remove a previously registered handler."""
    try:
        _notification_handlers.remove(handler)
    except ValueError:
        pass


async def dispatch_notification(
    server: str,
    method: str,
    params: Any,
) -> None:
    """
    Dispatch a notification to all registered handlers.
    Ignores exceptions in individual handlers.
    """
    for handler in list(_notification_handlers):
        try:
            await handler(server, method, params)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Gate logic helpers
# ---------------------------------------------------------------------------

def _channels_enabled() -> bool:
    """Runtime gate — override in tests / config."""
    import os
    return os.environ.get("CLAUDE_CODE_CHANNELS_ENABLED", "").lower() in (
        "1", "true"
    )


def gate_channel_server(
    server_name: str,
    capabilities: Optional[dict] = None,
    is_authenticated: bool = False,
    allowed_channels: Optional[list[str]] = None,
) -> ChannelGateResult:
    """
    Gate an MCP server's channel-notification path.

    Gate order (cheapest first):
      capability → runtime gate → auth → session

    Returns ChannelGateResult with action='register' or action='skip'.
    """
    # 1. Capability check: server must declare claude/channel experimental cap
    experimental = (capabilities or {}).get("experimental", {})
    if not experimental.get("claude/channel"):
        return ChannelGateResult(
            action="skip",
            kind=ChannelGateKind.CAPABILITY,
            reason="server did not declare claude/channel capability",
        )

    # 2. Runtime gate
    if not _channels_enabled():
        return ChannelGateResult(
            action="skip",
            kind=ChannelGateKind.DISABLED,
            reason="channels feature is not currently available",
        )

    # 3. Auth check
    if not is_authenticated:
        return ChannelGateResult(
            action="skip",
            kind=ChannelGateKind.AUTH,
            reason="channels requires authentication",
        )

    # 4. Session opt-in
    if allowed_channels is not None and server_name not in allowed_channels:
        return ChannelGateResult(
            action="skip",
            kind=ChannelGateKind.SESSION,
            reason=f"server {server_name} not in --channels list for this session",
        )

    return ChannelGateResult(action="register")

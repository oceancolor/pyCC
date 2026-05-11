"""
services/mcp/vscode_sdk_mcp.py — VSCode SDK MCP bidirectional communication.
Ported from services/mcp/vscodeSdkMcp.ts (112 lines).

Sets up the special internal VSCode MCP for bidirectional communication using
notifications, and sends experiment gate states to VSCode on connect.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Store the VSCode MCP client reference for sending notifications
_vscode_mcp_client: Optional[Any] = None


# ---------------------------------------------------------------------------
# Lazy helpers
# ---------------------------------------------------------------------------

def _log_for_debugging(msg: str) -> None:
    try:
        from claude_code.utils.debug import log_for_debugging
        log_for_debugging(msg)
    except (ImportError, Exception):
        logger.debug(msg)


def _log_event(event_name: str, data: dict) -> None:
    try:
        from claude_code.services.analytics import log_event
        log_event(event_name, data)
    except (ImportError, Exception):
        pass


def _check_statsig_feature_gate(gate: str) -> bool:
    try:
        from claude_code.services.analytics.growthbook import (
            check_statsig_feature_gate_cached_may_be_stale,
        )
        return check_statsig_feature_gate_cached_may_be_stale(gate)
    except (ImportError, Exception):
        return False


def _get_feature_value(key: str, default: Any) -> Any:
    try:
        from claude_code.services.analytics.growthbook import (
            get_feature_value_cached_may_be_stale,
        )
        return get_feature_value_cached_may_be_stale(key, default)
    except (ImportError, Exception):
        return default


def _read_auto_mode_enabled_state() -> Optional[str]:
    """
    Mirror of AutoModeEnabledState in permissionSetup — inlined because
    that file pulls in too many deps for this thin IPC module.
    """
    try:
        v = _get_feature_value("tengu_auto_mode_config", {})
        if isinstance(v, dict):
            enabled = v.get("enabled")
            if enabled in ("enabled", "disabled", "opt-in"):
                return enabled
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# LogEvent notification schema (Python equivalent)
# ---------------------------------------------------------------------------

def _validate_log_event_notification(notification: dict) -> Optional[dict]:
    """
    Validate a log_event notification from VSCode.
    Returns the parsed params if valid, None otherwise.
    Mirrors LogEventNotificationSchema (Zod).
    """
    if notification.get("method") != "log_event":
        return None
    params = notification.get("params")
    if not isinstance(params, dict):
        return None
    event_name = params.get("eventName")
    event_data = params.get("eventData")
    if not isinstance(event_name, str):
        return None
    if not isinstance(event_data, dict):
        return None
    return params


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def notify_vscode_file_updated(
    file_path: str,
    old_content: Optional[str],
    new_content: Optional[str],
) -> None:
    """
    Sends a file_updated notification to the VSCode MCP server.
    Used to notify VSCode when files are edited or written by Claude.
    Only fires when USER_TYPE=ant and the VSCode client is connected.
    """
    if os.environ.get("USER_TYPE") != "ant" or _vscode_mcp_client is None:
        return

    try:
        client = _vscode_mcp_client
        if hasattr(client, "notification"):
            # Fire-and-forget coroutine
            import asyncio
            coro = client.notification({
                "method": "file_updated",
                "params": {
                    "filePath": file_path,
                    "oldContent": old_content,
                    "newContent": new_content,
                },
            })
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(coro)
            except RuntimeError:
                pass  # No event loop — skip notification
    except Exception as e:
        _log_for_debugging(
            f"[VSCode] Failed to send file_updated notification: {e}"
        )


def setup_vscode_sdk_mcp(sdk_clients: list) -> None:
    """
    Sets up the special internal VSCode MCP for bidirectional communication
    using notifications.

    Finds the 'claude-vscode' client in sdk_clients, stores a reference,
    registers a notification handler for log_event, and immediately sends
    experiment gate states.
    """
    global _vscode_mcp_client

    # Find the claude-vscode client
    vscode_client = None
    for c in sdk_clients:
        name = getattr(c, "name", None) or (c.get("name") if isinstance(c, dict) else None)
        client_type = getattr(c, "type", None) or (c.get("type") if isinstance(c, dict) else None)
        if name == "claude-vscode" and client_type == "connected":
            vscode_client = c
            break

    if vscode_client is None:
        return

    # Store reference for later file-update notifications
    _vscode_mcp_client = vscode_client

    # Get the underlying MCP client object
    client = getattr(vscode_client, "client", None) or (
        vscode_client.get("client") if isinstance(vscode_client, dict) else None
    )
    if client is None:
        return

    # Register notification handler for log_event from VSCode
    if hasattr(client, "set_notification_handler"):
        def handle_log_event(notification: dict) -> None:
            params = _validate_log_event_notification(notification)
            if params:
                event_name = params["eventName"]
                event_data = params["eventData"]
                _log_event(
                    f"tengu_vscode_{event_name}",
                    event_data,
                )

        client.set_notification_handler("log_event", handle_log_event)

    # Send experiment gates to VSCode immediately
    gates: Dict[str, Any] = {
        "tengu_vscode_review_upsell": _check_statsig_feature_gate(
            "tengu_vscode_review_upsell"
        ),
        "tengu_vscode_onboarding": _check_statsig_feature_gate(
            "tengu_vscode_onboarding"
        ),
        # Browser support
        "tengu_quiet_fern": _get_feature_value("tengu_quiet_fern", False),
        # In-band OAuth via claude_authenticate
        "tengu_vscode_cc_auth": _get_feature_value("tengu_vscode_cc_auth", False),
    }

    # Tri-state: 'enabled' | 'disabled' | 'opt-in'. Omit if unknown so VSCode
    # fails closed (treats absent as 'disabled').
    auto_mode_state = _read_auto_mode_enabled_state()
    if auto_mode_state is not None:
        gates["tengu_auto_mode_state"] = auto_mode_state

    # Fire-and-forget experiment_gates notification
    try:
        import asyncio
        if hasattr(client, "notification"):
            coro = client.notification({
                "method": "experiment_gates",
                "params": {"gates": gates},
            })
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(coro)
            except RuntimeError:
                pass
    except Exception as e:
        _log_for_debugging(f"[VSCode] Failed to send experiment_gates: {e}")

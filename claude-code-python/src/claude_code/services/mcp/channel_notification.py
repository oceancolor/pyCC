"""MCP channel notifications. Ported from services/mcp/channelNotification.ts"""
from __future__ import annotations
from typing import Any, Callable

_notification_handlers: list = []

def register_notification_handler(handler: Callable) -> None:
    _notification_handlers.append(handler)

async def dispatch_notification(server: str, method: str, params: Any) -> None:
    for handler in _notification_handlers:
        try:
            await handler(server, method, params)
        except Exception:
            pass

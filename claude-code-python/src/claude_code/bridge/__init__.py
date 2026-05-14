"""Bridge package for Claude Code.

Provides the bridge between the REPL interface and the backend API,
including message types, request/response protocols, and the main
bridge client. Ported from the TypeScript bridge/ module.
"""
from __future__ import annotations

from claude_code.bridge.types import (
    BridgeApiClient,
    BridgeConfig,
    WorkData,
    WorkResponse,
)

__all__ = [
    "WorkData",
    "WorkResponse",
    "BridgeConfig",
    "BridgeApiClient",
]

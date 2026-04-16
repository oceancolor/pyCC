"""MCP in-process transport. Stub."""
from __future__ import annotations
from typing import Any


class InProcessTransport:
    async def send(self, message: Any) -> None:
        pass

    async def receive(self) -> Any:
        return None

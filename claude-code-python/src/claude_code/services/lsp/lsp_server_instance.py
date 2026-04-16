"""LSP server instance. Ported from services/lsp/LSPServerInstance.ts (511L → stub)."""
from __future__ import annotations
import asyncio
from typing import Any, List, Optional

from claude_code.services.lsp.lsp_client import LSPClient


class LSPServerInstance:
    """Manages a single LSP server process lifecycle."""

    def __init__(
        self,
        language_id: str,
        server_command: List[str],
        root_uri: str,
        cwd: str = ".",
    ):
        self.language_id = language_id
        self.server_command = server_command
        self.root_uri = root_uri
        self.cwd = cwd
        self.client: Optional[LSPClient] = None
        self._status = "stopped"

    @property
    def status(self) -> str:
        return self._status

    async def start(self) -> None:
        self.client = LSPClient(self.server_command, self.cwd)
        await self.client.start()
        await self.client.initialize(self.root_uri)
        self._status = "running"

    async def stop(self) -> None:
        if self.client:
            await self.client.stop()
        self._status = "stopped"

    async def request(self, method: str, params: Any = None) -> Any:
        if not self.client or not self.client.is_connected:
            return None
        return await self.client.request(method, params)

    async def notify(self, method: str, params: Any = None) -> None:
        if self.client and self.client.is_connected:
            await self.client.notify(method, params)

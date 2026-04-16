"""LSP client. Ported from services/lsp/LSPClient.ts (447L → stub)."""
from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional


class LSPClient:
    """Language Server Protocol client over stdio/TCP."""

    def __init__(self, server_command: List[str], cwd: str = "."):
        self.server_command = server_command
        self.cwd = cwd
        self._process: Optional[asyncio.subprocess.Process] = None
        self._request_id = 0
        self._connected = False

    async def start(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            *self.server_command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            cwd=self.cwd,
        )
        self._connected = True

    async def stop(self) -> None:
        if self._process:
            self._process.terminate()
            await self._process.wait()
            self._connected = False

    async def initialize(self, root_uri: str) -> dict:
        return await self.request("initialize", {
            "processId": None,
            "rootUri": root_uri,
            "capabilities": {},
        })

    async def request(self, method: str, params: Any = None) -> Any:
        """Send LSP request and return result. Stub."""
        return {}

    async def notify(self, method: str, params: Any = None) -> None:
        """Send LSP notification (no response expected). Stub."""
        pass

    @property
    def is_connected(self) -> bool:
        return self._connected

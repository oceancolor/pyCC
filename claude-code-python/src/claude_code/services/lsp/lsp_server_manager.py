"""LSP server manager. Ported from services/lsp/LSPServerManager.ts (420L → core)."""
from __future__ import annotations
import asyncio
from typing import Any, Dict, Optional

from claude_code.services.lsp.lsp_server_instance import LSPServerInstance


class LSPServerManager:
    """Manages multiple LSP server instances keyed by language ID."""

    def __init__(self):
        self._servers: Dict[str, LSPServerInstance] = {}

    async def get_or_start(
        self,
        language_id: str,
        server_command: list,
        root_uri: str,
        cwd: str = ".",
    ) -> LSPServerInstance:
        key = f"{language_id}:{root_uri}"
        if key not in self._servers:
            server = LSPServerInstance(language_id, server_command, root_uri, cwd)
            await server.start()
            self._servers[key] = server
        return self._servers[key]

    async def stop_all(self) -> None:
        for server in self._servers.values():
            await server.stop()
        self._servers.clear()

    def get_server(self, language_id: str, root_uri: str) -> Optional[LSPServerInstance]:
        return self._servers.get(f"{language_id}:{root_uri}")

    async def restart(self, language_id: str, root_uri: str) -> Optional[LSPServerInstance]:
        key = f"{language_id}:{root_uri}"
        server = self._servers.pop(key, None)
        if server:
            await server.stop()
            await server.start()
            self._servers[key] = server
        return server


_manager: Optional[LSPServerManager] = None


def get_lsp_server_manager() -> LSPServerManager:
    global _manager
    if _manager is None:
        _manager = LSPServerManager()
    return _manager

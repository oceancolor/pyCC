"""LSP manager stub. Ported from services/lsp/manager.ts"""
from __future__ import annotations
from typing import Any, Optional

class LSPManager:
    _instance: Optional["LSPManager"] = None

    @classmethod
    def get_instance(cls) -> "LSPManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    def is_running(self) -> bool:
        return False

    async def get_diagnostics(self, file_path: str) -> list:
        return []

    async def get_hover(self, file_path: str, line: int, character: int) -> Optional[dict]:
        return None

    async def get_definition(self, file_path: str, line: int, character: int) -> Optional[dict]:
        return None

    async def get_references(self, file_path: str, line: int, character: int) -> list:
        return []

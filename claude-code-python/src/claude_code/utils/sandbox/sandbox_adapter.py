"""Sandbox adapter stub. Ported from utils/sandbox/sandbox-adapter.ts"""
from __future__ import annotations
from typing import Optional

class SandboxManager:
    _instance: Optional["SandboxManager"] = None

    @classmethod
    def get_instance(cls) -> "SandboxManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def is_sandbox_active(self) -> bool:
        return False

    async def run_in_sandbox(self, command: str, **kwargs) -> dict:
        import asyncio
        from claude_code.utils.exec_utils import run_command
        return await run_command(command, **kwargs)

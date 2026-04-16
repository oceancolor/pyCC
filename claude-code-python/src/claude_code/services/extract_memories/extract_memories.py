"""Extract memories service stub. Ported from services/extractMemories."""
from __future__ import annotations
from typing import Any, Callable, Optional


def init_extract_memories() -> None:
    pass


async def run_extract_memories(context: Any, append_system_message: Any = None) -> None:
    pass


def create_auto_mem_can_use_tool(allowed_names: list = None) -> Callable:
    return lambda *args: True

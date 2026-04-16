"""Auto dream background memory consolidation stub. Ported from services/autoDream."""
from __future__ import annotations
from typing import Any, Callable, Optional

_runner: Optional[Callable] = None


def init_auto_dream() -> None:
    """Initialize auto dream runner."""
    global _runner
    _runner = None  # Stub: no-op until full memory system ported


async def run_auto_dream(context: Any, append_system_message: Any = None) -> None:
    if _runner:
        await _runner(context, append_system_message)

"""
Session memory extraction service.
Ported from services/SessionMemory/sessionMemory.ts (495 lines → core).
"""
from __future__ import annotations
from typing import Any, Callable, List, Optional

_last_memory_message_uuid: Optional[str] = None
_session_memory_initialized: bool = False


def reset_last_memory_message_uuid() -> None:
    global _last_memory_message_uuid
    _last_memory_message_uuid = None


def should_extract_memory(messages: List[Any]) -> bool:
    """Return True if memory extraction should be triggered."""
    if not messages:
        return False
    # Trigger on every N assistant turns
    assistant_count = sum(
        1 for m in messages
        if isinstance(m, dict) and m.get("role") == "assistant"
    )
    return assistant_count > 0 and assistant_count % 5 == 0


def init_session_memory() -> None:
    global _session_memory_initialized
    _session_memory_initialized = True


class ManualExtractionResult:
    def __init__(self, memories: List[str], session_id: str):
        self.memories = memories
        self.session_id = session_id


async def manually_extract_session_memory(
    messages: List[Any],
    model: Optional[str] = None,
) -> ManualExtractionResult:
    """Manually trigger memory extraction from current conversation."""
    # stub — full implementation requires API call
    return ManualExtractionResult(memories=[], session_id="")


def create_memory_file_can_use_tool(memory_path: str) -> Callable:
    """Create a can_use_tool function that only allows write to memory_path."""
    def can_use(tool_name: str, tool_input: dict) -> bool:
        if tool_name in ("Write", "Edit"):
            path = tool_input.get("file_path") or tool_input.get("path", "")
            return path == memory_path
        return tool_name in ("Read",)
    return can_use

"""Session memory utilities. Ported from services/SessionMemory/sessionMemoryUtils.ts (207L)"""
from __future__ import annotations
import re
from typing import Any, List, Optional


def extract_memory_blocks(text: str) -> List[str]:
    """Extract <memory> ... </memory> blocks from text."""
    return re.findall(r"<memory>(.*?)</memory>", text, re.DOTALL)


def format_memory_for_storage(memories: List[str], existing: str = "") -> str:
    """Format new memories for appending to memory file."""
    if not memories:
        return existing
    new_block = "\n".join(f"- {m.strip()}" for m in memories if m.strip())
    if existing:
        return existing.rstrip() + "\n\n" + new_block
    return new_block


def get_memory_extraction_prompt(messages: List[Any]) -> str:
    """Build prompt to extract memories from conversation."""
    return (
        "Please extract important facts, preferences, and context from this conversation "
        "that would be helpful to remember in future sessions. "
        "Format each memory as a concise bullet point inside <memory> tags."
    )

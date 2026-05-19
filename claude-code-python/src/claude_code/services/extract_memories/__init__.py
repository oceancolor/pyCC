"""Extract memories service.

Analyses a conversation transcript and extracts facts that are worth
preserving in long-term memory (``MEMORY.md``).  The extraction is
performed by a dedicated LLM call using a structured prompt.

Ported from: src/services/extractMemories/ (TypeScript)

Usage::

    from claude_code.services.extract_memories import (
        extract_memories,
        ExtractMemoriesResult,
        EXTRACT_MEMORIES_SYSTEM_PROMPT,
        build_extract_memories_prompt,
    )
"""
from __future__ import annotations

from claude_code.services.extract_memories.extract_memories import (
    extract_memories,
    ExtractMemoriesResult,
)
from claude_code.services.extract_memories.prompts import (
    EXTRACT_MEMORIES_SYSTEM_PROMPT,
    build_extract_memories_prompt,
)

__all__ = [
    "extract_memories",
    "ExtractMemoriesResult",
    "EXTRACT_MEMORIES_SYSTEM_PROMPT",
    "build_extract_memories_prompt",
]

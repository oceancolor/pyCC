"""
Team Memory Operations Utilities

Helper functions for identifying and summarizing team memory tool use.
Mirrors teamMemoryOps.ts.
"""

from __future__ import annotations

from typing import Any

from claude_code.memdir.team_mem_paths import is_team_mem_file
from claude_code.tools.file_edit_tool.constants import FILE_EDIT_TOOL_NAME
from claude_code.tools.file_write_tool.prompt import FILE_WRITE_TOOL_NAME

__all__ = [
    "is_team_mem_file",
    "is_team_memory_search",
    "is_team_memory_write_or_edit",
    "append_team_memory_summary_parts",
]


def is_team_memory_search(tool_input: Any) -> bool:
    """
    Check if a search tool use targets team memory files by examining its path.
    """
    if not tool_input or not isinstance(tool_input, dict):
        return False
    path = tool_input.get("path")
    if path and is_team_mem_file(path):
        return True
    return False


def is_team_memory_write_or_edit(tool_name: str, tool_input: Any) -> bool:
    """
    Check if a Write or Edit tool use targets a team memory file.
    """
    if tool_name not in (FILE_WRITE_TOOL_NAME, FILE_EDIT_TOOL_NAME):
        return False
    if not tool_input or not isinstance(tool_input, dict):
        return False
    file_path: str | None = tool_input.get("file_path") or tool_input.get("path")
    return file_path is not None and is_team_mem_file(file_path)


def append_team_memory_summary_parts(
    memory_counts: dict[str, int],
    is_active: bool,
    parts: list[str],
) -> None:
    """
    Append team memory summary parts to the parts array.
    Encapsulates all team memory verb/string logic for get_search_read_summary_text.

    Args:
        memory_counts: Dict with optional keys:
            - teamMemoryReadCount
            - teamMemorySearchCount
            - teamMemoryWriteCount
        is_active: Whether the action is currently in progress (affects verb tense).
        parts: Mutable list to append summary strings into.
    """
    team_read_count: int = memory_counts.get("teamMemoryReadCount", 0) or 0
    team_search_count: int = memory_counts.get("teamMemorySearchCount", 0) or 0
    team_write_count: int = memory_counts.get("teamMemoryWriteCount", 0) or 0

    if team_read_count > 0:
        if is_active:
            verb = "Recalling" if len(parts) == 0 else "recalling"
        else:
            verb = "Recalled" if len(parts) == 0 else "recalled"
        memory_word = "memory" if team_read_count == 1 else "memories"
        parts.append(f"{verb} {team_read_count} team {memory_word}")

    if team_search_count > 0:
        if is_active:
            verb = "Searching" if len(parts) == 0 else "searching"
        else:
            verb = "Searched" if len(parts) == 0 else "searched"
        parts.append(f"{verb} team memories")

    if team_write_count > 0:
        if is_active:
            verb = "Writing" if len(parts) == 0 else "writing"
        else:
            verb = "Wrote" if len(parts) == 0 else "wrote"
        memory_word = "memory" if team_write_count == 1 else "memories"
        parts.append(f"{verb} {team_write_count} team {memory_word}")

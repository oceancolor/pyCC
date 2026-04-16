"""
team_memory_ops.py - Team memory file operation utilities.

Ported from teamMemoryOps.ts.

Provides helpers for checking whether tool calls target team memory files,
and for building summary text about team memory operations.

The `is_team_mem_file` function is a stub — the real implementation checks
against a configured team memory directory path.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

# Tool name constants (mirrors TS imports from tool constants files)
FILE_EDIT_TOOL_NAME = "str_replace_based_edit_tool"
FILE_WRITE_TOOL_NAME = "write_file"

# Team memory directory marker — real impl reads from config / memdir
_TEAM_MEM_DIR_MARKER = ".claude/team_memory"


def is_team_mem_file(path: str) -> bool:
    """
    Return True if *path* refers to a team memory file.

    Stub: matches any path containing the team memory directory marker.
    Production code should check against the configured memdir path.
    """
    return _TEAM_MEM_DIR_MARKER in path


def is_team_memory_search(tool_input: Any) -> bool:
    """
    Return True if a search tool-use targets team memory files.

    Examines the ``path``, ``pattern``, or ``glob`` field of *tool_input*.
    """
    if not isinstance(tool_input, dict):
        return False
    path: Optional[str] = tool_input.get("path") or tool_input.get("pattern") or tool_input.get("glob")
    if path and is_team_mem_file(path):
        return True
    return False


def is_team_memory_write_or_edit(tool_name: str, tool_input: Any) -> bool:
    """
    Return True if a Write or Edit tool-use targets a team memory file.
    """
    if tool_name not in (FILE_WRITE_TOOL_NAME, FILE_EDIT_TOOL_NAME):
        return False
    if not isinstance(tool_input, dict):
        return False
    file_path: Optional[str] = tool_input.get("file_path") or tool_input.get("path")
    return file_path is not None and is_team_mem_file(file_path)


def append_team_memory_summary_parts(
    memory_counts: Dict[str, int],
    is_active: bool,
    parts: List[str],
) -> None:
    """
    Append human-readable team memory summary fragments to *parts*.

    Args:
        memory_counts: Dict with optional keys ``teamMemoryReadCount``,
                       ``teamMemorySearchCount``, ``teamMemoryWriteCount``.
        is_active:     True → use present-participle verbs ("Recalling");
                       False → use past-tense ("Recalled").
        parts:         Mutable list; fragments are appended in-place.
    """
    team_read = memory_counts.get("teamMemoryReadCount", 0)
    team_search = memory_counts.get("teamMemorySearchCount", 0)
    team_write = memory_counts.get("teamMemoryWriteCount", 0)

    def _verb(active_word: str, past_word: str) -> str:
        first = len(parts) == 0
        if is_active:
            return active_word if first else active_word.lower()
        return past_word if first else past_word.lower()

    if team_read > 0:
        verb = _verb("Recalling", "Recalled")
        mem_word = "memory" if team_read == 1 else "memories"
        parts.append(f"{verb} {team_read} team {mem_word}")

    if team_search > 0:
        verb = _verb("Searching", "Searched")
        parts.append(f"{verb} team memories")

    if team_write > 0:
        verb = _verb("Writing", "Wrote")
        mem_word = "memory" if team_write == 1 else "memories"
        parts.append(f"{verb} {team_write} team {mem_word}")

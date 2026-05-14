"""Memory utilities sub-package. Ported from utils/memory/.

Provides memory index management and path helpers for Claude's long-term
memory / CLAUDE.md storage.
"""
from __future__ import annotations

from claude_code.utils.memory.memory_paths import (
    ensure_memory_dir_exists,
    get_global_memory_path,
    get_memory_dir,
    get_projects_dir,
    get_session_memory_dir,
)

__all__ = [
    "get_memory_dir",
    "get_session_memory_dir",
    "get_projects_dir",
    "ensure_memory_dir_exists",
    "get_global_memory_path",
]

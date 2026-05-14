"""Memory path helpers. Ported from utils/memory/."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional


def get_memory_dir() -> str:
    """Return the directory that stores Claude's long-term memory files."""
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir

        return os.path.join(get_claude_config_home_dir(), "memory")
    except Exception:
        return str(Path.home() / ".claude" / "memory")


def get_session_memory_dir() -> str:
    """Return the directory that stores session-scoped memory snippets."""
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir

        return os.path.join(get_claude_config_home_dir(), "session-memory")
    except Exception:
        return str(Path.home() / ".claude" / "session-memory")


def get_projects_dir() -> str:
    """Return the directory that stores project conversation transcripts."""
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir

        return os.path.join(get_claude_config_home_dir(), "projects")
    except Exception:
        return str(Path.home() / ".claude" / "projects")


def ensure_memory_dir_exists() -> str:
    """Create and return the memory directory, creating it if necessary."""
    memory_dir = get_memory_dir()
    os.makedirs(memory_dir, exist_ok=True)
    return memory_dir


def get_global_memory_path() -> str:
    """Return the path to the global CLAUDE.md file in the config home."""
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir

        return os.path.join(get_claude_config_home_dir(), "CLAUDE.md")
    except Exception:
        return str(Path.home() / ".claude" / "CLAUDE.md")


def get_project_local_memory_path(project_root: str) -> str:
    """Return the path to the project-local CLAUDE.md file."""
    return os.path.join(project_root, "CLAUDE.md")


def get_local_memory_path(project_root: str) -> str:
    """Return the path to the machine-local (gitignored) CLAUDE.local.md file."""
    return os.path.join(project_root, ".claude", "local", "CLAUDE.md")

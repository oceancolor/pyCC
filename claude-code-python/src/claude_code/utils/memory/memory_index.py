"""Memory index and file detection utilities. Ported from utils/memoryFileDetection.ts and memory/"""

from __future__ import annotations

import os
import sys
from typing import Optional, Literal

MemoryType = Literal["User", "Project", "Local", "Managed", "AutoMem", "TeamMem"]

MEMORY_TYPE_VALUES: tuple = ("User", "Project", "Local", "Managed", "AutoMem")

_IS_WINDOWS = sys.platform == "win32"


def _to_posix(path: str) -> str:
    """Normalize path separators to forward slashes."""
    return path.replace("\\", "/")


def _to_comparable(path: str) -> str:
    """Return a stable string-comparable form of a path.

    On Windows: forward-slash separated and lowercased (case-insensitive FS).
    On other platforms: forward-slash separated only.
    """
    posix_form = _to_posix(path)
    return posix_form.lower() if _IS_WINDOWS else posix_form


def detect_session_file_type(
    file_path: str,
) -> Optional[Literal["session_memory", "session_transcript"]]:
    """Detect if a file path is a session-related file under the Claude config directory.

    Returns ``'session_memory'``, ``'session_transcript'``, or None.
    """
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir

        config_dir = get_claude_config_home_dir()
    except Exception:
        config_dir = os.path.expanduser("~/.claude")

    normalized = _to_comparable(file_path)
    config_dir_cmp = _to_comparable(config_dir)

    if not normalized.startswith(config_dir_cmp):
        return None

    if "/session-memory/" in normalized and normalized.endswith(".md"):
        return "session_memory"
    if "/projects/" in normalized and normalized.endswith(".jsonl"):
        return "session_transcript"
    return None


def detect_session_pattern_type(
    pattern: str,
) -> Optional[Literal["session_memory", "session_transcript"]]:
    """Check if a glob pattern indicates session file access intent.

    Used for Grep/Glob tools where we check patterns rather than actual paths.
    """
    normalized = _to_posix(pattern)

    if "session-memory" in normalized and (
        ".md" in normalized or normalized.endswith("*")
    ):
        return "session_memory"

    if ".jsonl" in normalized or (
        "projects" in normalized and "*.jsonl" in normalized
    ):
        return "session_transcript"

    return None


def is_memory_file(file_path: str) -> bool:
    """Return True if the file path refers to a Claude memory (CLAUDE.md) file."""
    basename = os.path.basename(file_path)
    return basename.upper() in ("CLAUDE.MD", ".CLAUDE.MD")


def get_project_memory_path(cwd: str) -> str:
    """Return the expected CLAUDE.md path for a project directory."""
    return os.path.join(cwd, "CLAUDE.md")


def project_is_in_git_repo(cwd: str) -> bool:
    """Return True if the given directory is inside a git repository.

    Performs a filesystem walk (no subprocess) looking for a ``.git`` directory.
    """
    current = os.path.abspath(cwd)
    while True:
        if os.path.exists(os.path.join(current, ".git")):
            return True
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return False

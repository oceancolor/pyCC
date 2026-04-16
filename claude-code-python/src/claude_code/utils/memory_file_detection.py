"""
memory_file_detection.py - Detect and classify Claude memory/session files.

Ported from memoryFileDetection.ts.
"""

from __future__ import annotations

import os
import re
import sys
from enum import Enum
from typing import Optional

IS_WINDOWS = sys.platform == "win32"


# ---------------------------------------------------------------------------
# Config stubs (wire to real config in production)
# ---------------------------------------------------------------------------

def _config_home() -> str:
    return os.path.expanduser("~/.claude")

def _memory_base() -> str:
    return os.path.expanduser("~/.claude/memory")

def _auto_mem_path() -> str:
    return os.path.expanduser("~/.claude/memdir")

def _auto_mem_enabled() -> bool:
    return bool(os.environ.get("CLAUDE_AUTO_MEMORY_ENABLED", ""))


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _to_posix(p: str) -> str:
    return p.replace("\\", "/")

def _comparable(p: str) -> str:
    s = _to_posix(p)
    return s.lower() if IS_WINDOWS else s


# ---------------------------------------------------------------------------
# Public enums
# ---------------------------------------------------------------------------

class SessionFileType(str, Enum):
    SESSION_MEMORY = "session_memory"
    SESSION_TRANSCRIPT = "session_transcript"

class MemoryScope(str, Enum):
    PERSONAL = "personal"
    TEAM = "team"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_session_file_type(file_path: str) -> Optional[SessionFileType]:
    """Returns SessionFileType if path is a Claude session file, else None."""
    config_cmp = _comparable(_config_home())
    norm = _comparable(file_path)
    if not norm.startswith(config_cmp):
        return None
    if "/session-memory/" in norm and norm.endswith(".md"):
        return SessionFileType.SESSION_MEMORY
    if "/projects/" in norm and norm.endswith(".jsonl"):
        return SessionFileType.SESSION_TRANSCRIPT
    return None


def detect_session_pattern_type(pattern: str) -> Optional[SessionFileType]:
    """Check if a glob/pattern string indicates session file access intent."""
    norm = _to_posix(pattern)
    if "session-memory" in norm and (".md" in norm or norm.endswith("*")):
        return SessionFileType.SESSION_MEMORY
    if ".jsonl" in norm or ("projects" in norm and "*.jsonl" in norm):
        return SessionFileType.SESSION_TRANSCRIPT
    return None


def is_auto_mem_file(file_path: str) -> bool:
    """Check if a file path is within the auto-memory (memdir) directory."""
    if not _auto_mem_enabled():
        return False
    auto_mem = _comparable(_auto_mem_path().rstrip("/\\"))
    norm = _comparable(file_path)
    return norm.startswith(auto_mem + "/") or norm == auto_mem


def is_auto_managed_memory_file(file_path: str) -> bool:
    """Check if a file is Claude-managed (excludes user CLAUDE.md files)."""
    return (
        is_auto_mem_file(file_path)
        or detect_session_file_type(file_path) is not None
        or _is_agent_mem_file(file_path)
    )


def is_memory_directory(dir_path: str) -> bool:
    """Check if a directory path is memory-related."""
    norm_cmp = _comparable(os.path.normpath(dir_path))

    if _auto_mem_enabled() and (
        "/agent-memory/" in norm_cmp or "/agent-memory-local/" in norm_cmp
    ):
        return True

    if _auto_mem_enabled():
        auto_cmp = _comparable(_auto_mem_path().rstrip("/\\"))
        if norm_cmp == auto_cmp or norm_cmp.startswith(auto_cmp + "/"):
            return True

    config_cmp = _comparable(_config_home())
    mem_base_cmp = _comparable(_memory_base())
    under_config = norm_cmp.startswith(config_cmp)
    under_base = norm_cmp.startswith(mem_base_cmp)

    if not under_config and not under_base:
        return False
    if "/session-memory/" in norm_cmp:
        return True
    if under_config and "/projects/" in norm_cmp:
        return True
    if _auto_mem_enabled() and "/memory/" in norm_cmp:
        return True
    return False


def is_shell_command_targeting_memory(command: str) -> bool:
    """Check if a shell command targets memory files."""
    dirs = [_config_home(), _memory_base()]
    if _auto_mem_enabled():
        dirs.append(_auto_mem_path().rstrip("/\\"))
    cmd_cmp = _comparable(command)
    if not any(cmd_cmp.find(_comparable(d)) != -1 for d in dirs if d):
        return False
    matches = re.findall(r"(?:[A-Za-z]:[/\\]|\/)[^\s'\"]+", command)
    for match in matches:
        clean = re.sub(r"[,;|&>]+$", "", match)
        if is_auto_managed_memory_file(clean) or is_memory_directory(clean):
            return True
    return False


def is_auto_managed_memory_pattern(pattern: str) -> bool:
    """Check if a glob/pattern targets auto-managed memory files only."""
    if detect_session_pattern_type(pattern) is not None:
        return True
    norm = pattern.replace("\\", "/")
    return _auto_mem_enabled() and (
        "agent-memory/" in norm or "agent-memory-local/" in norm
    )


def memory_scope_for_path(file_path: str) -> Optional[MemoryScope]:
    """Determine which memory store (if any) a path belongs to."""
    return MemoryScope.PERSONAL if is_auto_mem_file(file_path) else None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _is_agent_mem_file(file_path: str) -> bool:
    if not _auto_mem_enabled():
        return False
    norm = _comparable(file_path)
    return "/agent-memory/" in norm or "/agent-memory-local/" in norm

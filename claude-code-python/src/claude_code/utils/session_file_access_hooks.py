# Source: utils/sessionFileAccessHooks.ts
"""
Session file access analytics hooks.
Tracks access to session memory and transcript files via Read, Grep, Glob tools.
Also tracks memdir file access via Read, Grep, Glob, Edit, and Write tools.

Note: In Python port, analytics/event logging is stubbed out.
The core data model (FileAccessRecord, SessionFileAccessTracker) is preserved.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional

# ---------------------------------------------------------------------------
# Constants (matching TS tool name strings)
# ---------------------------------------------------------------------------

FILE_READ_TOOL_NAME = "Read"
FILE_EDIT_TOOL_NAME = "Edit"
FILE_WRITE_TOOL_NAME = "Write"
GLOB_TOOL_NAME = "Glob"
GREP_TOOL_NAME = "Grep"

# Patterns that indicate session memory / transcript files
_SESSION_MEMORY_PATTERNS = (
    ".claude/memory",
    "CLAUDE.md",
    "claude_memory",
)
_SESSION_TRANSCRIPT_PATTERNS = (
    ".claude/conversations",
    "session_transcript",
    "transcript.jsonl",
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


class FileOperation(str, Enum):
    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    GLOB = "glob"
    GREP = "grep"


@dataclass
class FileAccessRecord:
    """Record of a single file access event."""

    path: str
    operation: FileOperation
    timestamp: float = field(default_factory=time.time)

    def __repr__(self) -> str:
        return (
            f"FileAccessRecord(path={self.path!r}, "
            f"operation={self.operation.value!r}, "
            f"timestamp={self.timestamp})"
        )


# ---------------------------------------------------------------------------
# Detection helpers (ported from memoryFileDetection.ts logic)
# ---------------------------------------------------------------------------


def detect_session_file_type(
    path: str,
) -> Optional[str]:
    """
    Returns 'session_memory', 'session_transcript', or None.
    Mirrors detectSessionFileType from memoryFileDetection.ts.
    """
    lower = path.lower()
    for pat in _SESSION_MEMORY_PATTERNS:
        if pat.lower() in lower:
            return "session_memory"
    for pat in _SESSION_TRANSCRIPT_PATTERNS:
        if pat.lower() in lower:
            return "session_transcript"
    return None


def detect_session_pattern_type(pattern: str) -> Optional[str]:
    """Detect session file type from a glob/grep pattern."""
    return detect_session_file_type(pattern)


def is_auto_mem_file(path: str) -> bool:
    """Returns True if path looks like an auto-managed memory (memdir) file."""
    lower = path.lower()
    return ".claude/memory" in lower or "memdir" in lower


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class SessionFileAccessTracker:
    """
    Tracks file accesses during a session.
    Thread-safe append operations (list.append is GIL-protected in CPython).
    """

    def __init__(self) -> None:
        self._records: List[FileAccessRecord] = []
        self._hooks: List[Callable[[FileAccessRecord], None]] = []

    # -- recording -----------------------------------------------------------

    def record_read(self, path: str) -> None:
        """Record a file read access."""
        self._add(path, FileOperation.READ)

    def record_write(self, path: str) -> None:
        """Record a file write access."""
        self._add(path, FileOperation.WRITE)

    def record_edit(self, path: str) -> None:
        """Record a file edit access."""
        self._add(path, FileOperation.EDIT)

    def record_glob(self, pattern: str) -> None:
        """Record a glob pattern access."""
        self._add(pattern, FileOperation.GLOB)

    def record_grep(self, path: str) -> None:
        """Record a grep access."""
        self._add(path, FileOperation.GREP)

    def _add(self, path: str, operation: FileOperation) -> None:
        record = FileAccessRecord(path=path, operation=operation)
        self._records.append(record)
        for hook in self._hooks:
            try:
                hook(record)
            except Exception:
                pass

    # -- querying ------------------------------------------------------------

    def get_accessed_files(
        self,
        operation: Optional[FileOperation] = None,
    ) -> List[FileAccessRecord]:
        """
        Return all access records, optionally filtered by operation type.
        Returns a snapshot (copy).
        """
        records = list(self._records)
        if operation is not None:
            records = [r for r in records if r.operation == operation]
        return records

    def get_unique_paths(
        self,
        operation: Optional[FileOperation] = None,
    ) -> List[str]:
        """Return unique file paths accessed, preserving first-seen order."""
        seen: Dict[str, bool] = {}
        for r in self.get_accessed_files(operation):
            seen.setdefault(r.path, True)
        return list(seen.keys())

    def clear(self) -> None:
        """Reset all records (e.g. between sessions)."""
        self._records.clear()

    # -- hooks ---------------------------------------------------------------

    def add_hook(self, callback: Callable[[FileAccessRecord], None]) -> None:
        """Register a callback invoked on every new record."""
        self._hooks.append(callback)

    def remove_hook(self, callback: Callable[[FileAccessRecord], None]) -> None:
        """Remove a previously registered hook."""
        try:
            self._hooks.remove(callback)
        except ValueError:
            pass

    # -- tool dispatch -------------------------------------------------------

    def handle_tool_use(
        self,
        tool_name: str,
        tool_input: dict,
    ) -> None:
        """
        Process a PostToolUse event.
        Mirrors handleSessionFileAccess from the TS source.
        """
        if tool_name == FILE_READ_TOOL_NAME:
            path = tool_input.get("file_path", "")
            if path:
                self.record_read(path)
                if is_auto_mem_file(path):
                    pass  # analytics stub: tengu_memdir_file_read

        elif tool_name == FILE_EDIT_TOOL_NAME:
            path = tool_input.get("file_path", "")
            if path:
                self.record_edit(path)
                if is_auto_mem_file(path):
                    pass  # analytics stub: tengu_memdir_file_edit

        elif tool_name == FILE_WRITE_TOOL_NAME:
            path = tool_input.get("file_path", "")
            if path:
                self.record_write(path)
                if is_auto_mem_file(path):
                    pass  # analytics stub: tengu_memdir_file_write

        elif tool_name == GLOB_TOOL_NAME:
            pattern = tool_input.get("pattern", "")
            if pattern:
                self.record_glob(pattern)

        elif tool_name == GREP_TOOL_NAME:
            path = tool_input.get("path", "") or tool_input.get("glob", "")
            if path:
                self.record_grep(path)

        # Session file type detection (for analytics)
        file_type = _get_session_file_type_from_input(tool_name, tool_input)
        if file_type == "session_memory":
            pass  # analytics stub: tengu_session_memory_accessed
        elif file_type == "session_transcript":
            pass  # analytics stub: tengu_transcript_accessed


def _get_session_file_type_from_input(
    tool_name: str, tool_input: dict
) -> Optional[str]:
    """Extract session file type from tool inputs."""
    if tool_name == FILE_READ_TOOL_NAME:
        path = tool_input.get("file_path", "")
        return detect_session_file_type(path) if path else None

    if tool_name == GREP_TOOL_NAME:
        path = tool_input.get("path", "")
        if path:
            t = detect_session_file_type(path)
            if t:
                return t
        glob = tool_input.get("glob", "")
        if glob:
            return detect_session_pattern_type(glob)
        return None

    if tool_name == GLOB_TOOL_NAME:
        path = tool_input.get("path", "")
        if path:
            t = detect_session_file_type(path)
            if t:
                return t
        pattern = tool_input.get("pattern", "")
        return detect_session_pattern_type(pattern) if pattern else None

    return None


def is_memory_file_access(tool_name: str, tool_input: dict) -> bool:
    """
    Check if a tool use constitutes a memory file access.
    Mirrors isMemoryFileAccess from the TS source.
    """
    if _get_session_file_type_from_input(tool_name, tool_input) == "session_memory":
        return True
    path = tool_input.get("file_path", "")
    if path and is_auto_mem_file(path):
        return True
    return False


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_tracker: Optional[SessionFileAccessTracker] = None


def get_tracker() -> SessionFileAccessTracker:
    """Return the module-level singleton SessionFileAccessTracker."""
    global _tracker
    if _tracker is None:
        _tracker = SessionFileAccessTracker()
    return _tracker


def reset_tracker() -> None:
    """Reset the singleton (useful for tests)."""
    global _tracker
    _tracker = None

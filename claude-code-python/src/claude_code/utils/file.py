"""
File utilities
原始 TS: src/utils/file.ts (partial port of core functions)
"""
from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_OUTPUT_SIZE = int(0.25 * 1024 * 1024)  # 0.25 MB in bytes
FILE_NOT_FOUND_CWD_NOTE = "Note: The file was not found relative to the current working directory."


# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------

async def path_exists(path: str) -> bool:
    """Check if a path exists asynchronously."""
    return os.path.exists(path)


def read_file_safe(filepath: str) -> Optional[str]:
    """Read a file safely, returning None on error."""
    try:
        with open(filepath, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def get_file_modification_time(file_path: str) -> int:
    """
    Get normalized modification time in milliseconds.
    Uses floor to ensure consistent comparisons.
    """
    s = os.stat(file_path)
    return int(s.st_mtime * 1000)


async def get_file_modification_time_async(file_path: str) -> int:
    """Async variant of get_file_modification_time."""
    s = os.stat(file_path)
    return int(s.st_mtime * 1000)


def write_text_content(
    file_path: str,
    content: str,
    encoding: str = "utf-8",
    endings: str = "LF",  # 'LF' | 'CRLF'
) -> None:
    """Write text content with line-ending normalization."""
    to_write = content
    if endings == "CRLF":
        # Normalize existing CRLF → LF first, then convert LF → CRLF
        to_write = content.replace("\r\n", "\n").replace("\n", "\r\n")
    with open(file_path, "w", encoding=encoding, newline="") as f:
        f.write(to_write)


def add_line_numbers(content: str, start: int = 1) -> str:
    """Add line numbers to content."""
    lines = content.splitlines(keepends=True)
    width = len(str(start + len(lines) - 1))
    result = []
    for i, line in enumerate(lines):
        result.append(f"{start + i:>{width}}\t{line}")
    return "".join(result)


def find_similar_file(file_path: str, cwd: str) -> Optional[str]:
    """
    Try to find a similar file in cwd when exact path not found.
    Returns suggested path or None.
    """
    basename = os.path.basename(file_path)
    # Simple case-insensitive search
    for root, dirs, files in os.walk(cwd):
        for fname in files:
            if fname.lower() == basename.lower():
                return os.path.join(root, fname)
    return None


def suggest_path_under_cwd(file_path: str, cwd: str) -> Optional[str]:
    """Suggest that the path should be relative to cwd."""
    if not os.path.isabs(file_path):
        candidate = os.path.join(cwd, file_path)
        if os.path.exists(candidate):
            return candidate
    return None


def format_file_size(size_in_bytes: int) -> str:
    """Format byte count to human-readable string."""
    kb = size_in_bytes / 1024
    if kb < 1:
        return f"{size_in_bytes} bytes"
    if kb < 1024:
        val = f"{kb:.1f}".rstrip("0").rstrip(".")
        return f"{val}KB"
    mb = kb / 1024
    if mb < 1024:
        val = f"{mb:.1f}".rstrip("0").rstrip(".")
        return f"{val}MB"
    gb = mb / 1024
    val = f"{gb:.1f}".rstrip("0").rstrip(".")
    return f"{val}GB"

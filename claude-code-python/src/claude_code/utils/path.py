"""
Path utilities
原始 TS: src/utils/path.ts
"""
from __future__ import annotations

import os
import unicodedata
from pathlib import Path
from typing import Optional


def expand_path(path: str, base_dir: Optional[str] = None) -> str:
    """
    Expand a path that may contain tilde notation (~) to an absolute path.
    Returns NFC-normalized path.
    原始 TS: expandPath
    """
    if not isinstance(path, str):
        raise TypeError(f"Path must be a string, received {type(path)}")

    actual_base = base_dir or os.getcwd()

    if "\x00" in path or "\x00" in actual_base:
        raise ValueError("Path contains null bytes")

    trimmed = path.strip()
    if not trimmed:
        return unicodedata.normalize("NFC", os.path.normpath(actual_base))

    if trimmed == "~":
        return unicodedata.normalize("NFC", str(Path.home()))

    expanded = os.path.expanduser(trimmed)

    if os.path.isabs(expanded):
        return unicodedata.normalize("NFC", os.path.normpath(expanded))

    # Relative path: resolve against base_dir
    result = os.path.normpath(os.path.join(actual_base, expanded))
    return unicodedata.normalize("NFC", result)


def to_relative_path(abs_path: str, base_dir: Optional[str] = None) -> str:
    """
    Convert an absolute path to a relative path from base_dir.
    Falls back to the absolute path if it can't be made relative.
    原始 TS: toRelativePath
    """
    base = base_dir or os.getcwd()
    try:
        return os.path.relpath(abs_path, base)
    except ValueError:
        # On Windows, different drives can't be made relative
        return abs_path


def is_path_within(path: str, ancestor: str) -> bool:
    """Check if path is within ancestor directory."""
    path_parts = Path(os.path.realpath(path)).parts
    ancestor_parts = Path(os.path.realpath(ancestor)).parts
    return path_parts[: len(ancestor_parts)] == ancestor_parts

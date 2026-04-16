"""Glob utility functions - Python port of glob.ts."""

import fnmatch
import os
import re
from pathlib import Path
from typing import Optional


# Characters that make a string a glob pattern
_GLOB_CHARS_RE = re.compile(r'[*?\[{]')


def is_glob_pattern(s: str) -> bool:
    """Return True if the string contains glob special characters."""
    return bool(_GLOB_CHARS_RE.search(s))


def extract_glob_base_directory(pattern: str) -> tuple[str, str]:
    """Extract the static base directory from a glob pattern.

    Returns (base_dir, relative_pattern).
    """
    match = _GLOB_CHARS_RE.search(pattern)

    if not match:
        # No glob characters — literal path
        base_dir = str(Path(pattern).parent)
        filename = Path(pattern).name
        return base_dir, filename

    static_prefix = pattern[: match.start()]
    last_sep = max(static_prefix.rfind('/'), static_prefix.rfind(os.sep))

    if last_sep == -1:
        return '', pattern

    base_dir = static_prefix[:last_sep]
    relative_pattern = pattern[last_sep + 1 :]

    if base_dir == '' and last_sep == 0:
        base_dir = '/'

    return base_dir, relative_pattern


def expand_glob(
    pattern: str,
    cwd: str,
    *,
    limit: int = 1000,
    offset: int = 0,
    hidden: bool = True,
    respect_gitignore: bool = False,
) -> dict:
    """Expand a glob pattern relative to cwd.

    Returns {'files': [...], 'truncated': bool}.
    Uses pathlib.Path.rglob / glob for matching.
    """
    search_dir = cwd
    search_pattern = pattern

    # Handle absolute patterns
    if os.path.isabs(pattern):
        base_dir, rel_pattern = extract_glob_base_directory(pattern)
        if base_dir:
            search_dir = base_dir
            search_pattern = rel_pattern

    base = Path(search_dir)
    if not base.is_dir():
        return {'files': [], 'truncated': False}

    try:
        matched = sorted(
            base.rglob(search_pattern) if '**' in search_pattern else base.glob(search_pattern),
            key=lambda p: p.stat().st_mtime,
        )
    except (OSError, ValueError):
        matched = []

    all_paths = []
    for p in matched:
        if not hidden and p.name.startswith('.'):
            continue
        if p.is_file():
            all_paths.append(str(p.resolve()))

    truncated = len(all_paths) > offset + limit
    files = all_paths[offset : offset + limit]
    return {'files': files, 'truncated': truncated}

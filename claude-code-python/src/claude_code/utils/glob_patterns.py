"""
Glob patterns module - wraps glob_utils with additional path-based glob function.
Ported from glob.ts
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional

# Re-export from glob_utils
from claude_code.utils.glob_utils import (
    expand_glob,
    is_glob_pattern,
    extract_glob_base_directory,
)


def glob(
    pattern: str,
    cwd: Optional[str] = None,
    limit: int = 1000,
    offset: int = 0,
    include_hidden: bool = False,
) -> List[str]:
    """
    Expand a glob pattern relative to cwd, return matching paths.

    Args:
        pattern: Glob pattern (absolute or relative)
        cwd: Working directory for relative patterns
        limit: Maximum results to return
        offset: Skip this many results
        include_hidden: Include hidden files/dirs (starting with .)

    Returns:
        List of absolute path strings
    """
    base = Path(cwd) if cwd else Path.cwd()

    # Determine if pattern is absolute
    p = Path(pattern)
    if p.is_absolute():
        search_root = p.parent
        rel_pattern = p.name
    else:
        # Extract static base directory from pattern
        result = extract_glob_base_directory(pattern)
        base_dir = result.get("base_dir", "") if isinstance(result, dict) else ""
        rel_part = result.get("relative_pattern", pattern) if isinstance(result, dict) else pattern
        search_root = base / base_dir if base_dir else base
        rel_pattern = rel_part

    matches: List[str] = []
    try:
        for match in sorted(search_root.glob(rel_pattern)):
            # Skip hidden files unless requested
            parts = match.relative_to(search_root).parts
            if not include_hidden and any(p.startswith(".") for p in parts):
                continue
            matches.append(str(match))
    except (OSError, ValueError):
        pass

    return matches[offset: offset + limit]


__all__ = [
    "glob",
    "expand_glob",
    "is_glob_pattern",
    "extract_glob_base_directory",
]

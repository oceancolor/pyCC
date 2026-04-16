# 原始 TS: utils/ripgrep.ts
"""Ripgrep (rg) subprocess wrapper for fast code/text search."""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class RipgrepConfig:
    """Describes how to invoke ripgrep on this system."""
    mode: str  # "system" | "builtin" | "embedded"
    command: str
    args: List[str] = field(default_factory=list)
    argv0: Optional[str] = None


# ---------------------------------------------------------------------------
# Executable discovery
# ---------------------------------------------------------------------------

def find_ripgrep() -> RipgrepConfig:
    """Locate the ripgrep executable, preferring bundled → system."""
    # 1. Check for a bundled/embedded rg shipped alongside this package
    embedded = _find_embedded_rg()
    if embedded:
        return RipgrepConfig(mode="embedded", command=embedded)

    # 2. Fall back to system rg on PATH
    system = shutil.which("rg")
    if system:
        return RipgrepConfig(mode="system", command=system)

    raise FileNotFoundError(
        "ripgrep (rg) not found. Install it via your package manager or "
        "ensure the bundled binary is present."
    )


def _find_embedded_rg() -> Optional[str]:
    """Return path to the bundled rg binary, or None."""
    # Look next to this package's __file__ (e.g., shipped in vendor/ dir)
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", "..", "vendor", "rg"),
        os.path.join(here, "..", "..", "bin", "rg"),
    ]
    for path in candidates:
        path = os.path.normpath(path)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


# ---------------------------------------------------------------------------
# Public search helpers
# ---------------------------------------------------------------------------

@dataclass
class RipgrepMatch:
    """A single line match from ripgrep output."""
    file: str
    line_number: int
    line: str


async def rg_search(
    pattern: str,
    paths: List[str],
    *,
    case_sensitive: bool = False,
    whole_word: bool = False,
    fixed_strings: bool = False,
    include_glob: Optional[str] = None,
    exclude_glob: Optional[str] = None,
    max_count: Optional[int] = None,
    context_lines: int = 0,
    extra_args: Optional[List[str]] = None,
) -> List[RipgrepMatch]:
    """Run ripgrep and return a list of matches.

    Args:
        pattern: The search pattern (regex or literal).
        paths: Directories or files to search.
        case_sensitive: Enable case-sensitive matching.
        whole_word: Match whole words only.
        fixed_strings: Treat pattern as a literal string.
        include_glob: Only search files matching this glob.
        exclude_glob: Exclude files matching this glob.
        max_count: Stop after this many matches.
        context_lines: Number of context lines around each match.
        extra_args: Additional raw rg arguments.
    """
    config = find_ripgrep()
    cmd = [config.command] + config.args

    # Flags
    if not case_sensitive:
        cmd.append("--ignore-case")
    if whole_word:
        cmd.append("--word-regexp")
    if fixed_strings:
        cmd.append("--fixed-strings")
    if include_glob:
        cmd += ["--glob", include_glob]
    if exclude_glob:
        cmd += ["--glob", f"!{exclude_glob}"]
    if max_count is not None:
        cmd += ["--max-count", str(max_count)]
    if context_lines > 0:
        cmd += ["--context", str(context_lines)]
    if extra_args:
        cmd += extra_args

    # Output in a parseable format
    cmd += ["--line-number", "--with-filename", "--color", "never"]
    cmd.append("--")
    cmd.append(pattern)
    cmd += paths

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, _ = await proc.communicate()

    matches: List[RipgrepMatch] = []
    for raw_line in stdout.decode(errors="replace").splitlines():
        parsed = _parse_rg_line(raw_line)
        if parsed:
            matches.append(parsed)
    return matches


def rg_search_sync(
    pattern: str,
    paths: List[str],
    **kwargs,
) -> List[RipgrepMatch]:
    """Synchronous wrapper around :func:`rg_search`."""
    return asyncio.run(rg_search(pattern, paths, **kwargs))


def _parse_rg_line(line: str) -> Optional[RipgrepMatch]:
    """Parse a ``file:lineno:content`` line from ripgrep output."""
    # ripgrep --line-number --with-filename output: PATH:LINENO:CONTENT
    parts = line.split(":", 2)
    if len(parts) < 3:
        return None
    try:
        return RipgrepMatch(
            file=parts[0],
            line_number=int(parts[1]),
            line=parts[2],
        )
    except (ValueError, IndexError):
        return None


# ---------------------------------------------------------------------------
# Count characters in a string (used by ripgrep.ts)
# ---------------------------------------------------------------------------

def count_char_in_string(s: str, char: str) -> int:
    """Count occurrences of *char* in *s*."""
    return s.count(char)

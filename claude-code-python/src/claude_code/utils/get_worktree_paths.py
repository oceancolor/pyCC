"""
Get worktree paths - Python port of getWorktreePaths.ts

Returns the paths of all worktrees for the current git repository.
If git is not available, not in a git repo, or has only one worktree,
returns an empty array.
"""
from __future__ import annotations

import os
import subprocess
import time
import unicodedata
from typing import List, Optional


def _log_event(event_name: str, data: dict) -> None:
    """Fire-and-forget analytics event. Silently swallows errors."""
    try:
        from claude_code.services.analytics import log_event  # type: ignore
        log_event(event_name, data)
    except Exception:
        pass


def _git_exe() -> str:
    """Return the git executable (env-override or default 'git')."""
    return os.environ.get("GIT_EXECUTABLE", "git")


def get_worktree_paths(cwd: str) -> List[str]:
    """Return absolute paths of all git worktrees rooted at cwd.

    Current worktree comes first; others are sorted alphabetically.
    Returns empty list if git is unavailable, not a repo, or single-tree.
    """
    start_ms = int(time.time() * 1000)

    try:
        result = subprocess.run(
            [_git_exe(), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=cwd,
        )
        code = result.returncode
        stdout = result.stdout
    except FileNotFoundError:
        code = 1
        stdout = ""

    duration_ms = int(time.time() * 1000) - start_ms

    if code != 0:
        _log_event("tengu_worktree_detection", {
            "duration_ms": duration_ms,
            "worktree_count": 0,
            "success": False,
        })
        return []

    # Parse porcelain output: lines starting with "worktree " contain paths
    worktree_paths: List[str] = []
    for line in stdout.splitlines():
        if line.startswith("worktree "):
            raw_path = line[len("worktree "):]
            # NFC-normalize (mirrors TS .normalize('NFC'))
            normalized = unicodedata.normalize("NFC", raw_path)
            worktree_paths.append(normalized)

    _log_event("tengu_worktree_detection", {
        "duration_ms": duration_ms,
        "worktree_count": len(worktree_paths),
        "success": True,
    })

    # Sort: current worktree first, then alphabetically
    sep = os.sep
    current: Optional[str] = None
    for p in worktree_paths:
        if cwd == p or cwd.startswith(p + sep):
            current = p
            break

    others = sorted(p for p in worktree_paths if p != current)
    return [current, *others] if current else others

"""
Git utilities
原始 TS: src/utils/git.ts (partial port)

gitpython + subprocess
"""
from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional

_GIT_ROOT_NOT_FOUND = object()


def find_git_root(start_path: Optional[str] = None) -> Optional[str]:
    """
    Find the root of the git repository containing start_path.
    Returns None if not inside a git repo.
    原始 TS: findGitRoot
    """
    current = os.path.realpath(start_path or os.getcwd())

    while True:
        git_path = os.path.join(current, ".git")
        if os.path.exists(git_path):
            return current

        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    return None


def get_git_branch(cwd: Optional[str] = None) -> Optional[str]:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_git_remote_url(cwd: Optional[str] = None) -> Optional[str]:
    """Get the remote URL of the git repo."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def get_git_head(cwd: Optional[str] = None) -> Optional[str]:
    """Get the current HEAD commit hash."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=cwd or os.getcwd(),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def is_git_repo(path: Optional[str] = None) -> bool:
    """Check if path is inside a git repository."""
    return find_git_root(path) is not None

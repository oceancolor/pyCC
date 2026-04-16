"""Filesystem-based git state reading. Ported from utils/git/gitFilesystem.ts"""
from __future__ import annotations
import asyncio
import os
import re
from pathlib import Path
from typing import Optional


async def resolve_git_dir(path: str) -> Optional[str]:
    """Find the .git directory for a given path."""
    p = Path(path)
    while p != p.parent:
        git = p / ".git"
        if git.is_dir():
            return str(git)
        if git.is_file():
            # Worktree: .git file contains gitdir: <path>
            content = git.read_text().strip()
            m = re.match(r'gitdir:\s*(.+)', content)
            if m:
                return str((git.parent / m.group(1).strip()).resolve())
        p = p.parent
    return None


async def read_head(git_dir: str) -> Optional[str]:
    """Read current branch or commit SHA from HEAD."""
    try:
        head = (Path(git_dir) / "HEAD").read_text().strip()
        if head.startswith("ref: refs/heads/"):
            return head[len("ref: refs/heads/"):]
        return head  # detached HEAD = raw SHA
    except Exception:
        return None

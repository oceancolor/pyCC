"""Portable worktree path detection. Ported from utils/getWorktreePathsPortable.ts"""
from __future__ import annotations
import asyncio
import subprocess
from typing import List


async def get_worktree_paths_portable(cwd: str) -> List[str]:
    """Return all git worktree paths for the repository rooted at *cwd*.

    Uses only ``subprocess`` (no analytics, no bootstrap deps) so it can
    be called from lightweight SDK contexts that don't load the full CLI
    dependency chain.

    Ported from utils/getWorktreePathsPortable.ts: getWorktreePathsPortable.

    Args:
        cwd: Working directory used as the git root hint.

    Returns:
        List of absolute worktree paths (NFC-normalised on macOS).  Empty
        list if git is unavailable or *cwd* is not inside a repository.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "worktree", "list", "--porcelain",
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        if not stdout:
            return []
        lines = stdout.decode("utf-8", errors="replace").splitlines()
        paths = [
            line[len("worktree "):].strip()
            for line in lines
            if line.startswith("worktree ")
        ]
        # Normalise to NFC (mirrors .normalize('NFC') in the TS version)
        import unicodedata
        return [unicodedata.normalize("NFC", p) for p in paths]
    except Exception:
        return []


def get_worktree_paths_portable_sync(cwd: str) -> List[str]:
    """Synchronous variant for non-async call-sites."""
    try:
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            cwd=cwd,
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout:
            return []
        lines = result.stdout.decode("utf-8", errors="replace").splitlines()
        paths = [
            line[len("worktree "):].strip()
            for line in lines
            if line.startswith("worktree ")
        ]
        import unicodedata
        return [unicodedata.normalize("NFC", p) for p in paths]
    except Exception:
        return []

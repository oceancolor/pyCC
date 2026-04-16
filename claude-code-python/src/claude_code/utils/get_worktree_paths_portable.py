"""Portable worktree path detection. Ported from getWorktreePathsPortable.ts"""
from __future__ import annotations
import asyncio
from typing import List

async def get_worktree_paths_portable(cwd: str) -> List[str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            'git', 'worktree', 'list', '--porcelain',
            cwd=cwd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        lines = stdout.decode(errors='replace').splitlines()
        return [l[len('worktree '):] for l in lines if l.startswith('worktree ')]
    except Exception:
        return []

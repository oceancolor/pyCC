"""Gitignore utilities. Ported from utils/git/gitignore.ts"""
from __future__ import annotations
import asyncio
import os


async def is_path_gitignored(file_path: str, cwd: str) -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git", "check-ignore", file_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            cwd=cwd)
        await asyncio.wait_for(proc.wait(), timeout=3.0)
        return proc.returncode == 0
    except Exception:
        return False


async def add_to_gitignore(pattern: str, gitignore_path: str) -> None:
    try:
        with open(gitignore_path, "a") as f:
            f.write(f"\n{pattern}\n")
    except Exception:
        pass

"""gh CLI auth status. Ported from utils/github/ghAuthStatus.ts"""
from __future__ import annotations
import asyncio
import shutil
from typing import Literal

GhAuthStatus = Literal["authenticated", "not_authenticated", "not_installed"]


async def get_gh_auth_status() -> GhAuthStatus:
    if not shutil.which("gh"):
        return "not_installed"
    try:
        proc = await asyncio.create_subprocess_exec(
            "gh", "auth", "token",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL)
        await asyncio.wait_for(proc.wait(), timeout=5.0)
        return "authenticated" if proc.returncode == 0 else "not_authenticated"
    except Exception:
        return "not_authenticated"

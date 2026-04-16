"""
which.py - Find the full path to a command executable.

Ported from which.ts.

Provides:
  which(command) -> Optional[str]       # async
  which_sync(command) -> Optional[str]  # sync

Uses the standard-library ``shutil.which`` as the primary backend (fast,
no subprocess), with a subprocess fallback that mirrors the TS behaviour
(``where.exe`` on Windows, ``which`` on POSIX).
"""

from __future__ import annotations

import asyncio
import platform
import shutil
import subprocess
from typing import Optional


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _which_shutil(command: str) -> Optional[str]:
    """Use shutil.which — fast, no subprocess required."""
    return shutil.which(command)


def _which_subprocess_sync(command: str) -> Optional[str]:
    """
    Subprocess fallback (mirrors TS whichNodeSync).
    Uses ``where.exe`` on Windows, ``which`` on POSIX.
    """
    is_windows = platform.system() == "Windows"
    shell_cmd = f"where.exe {command}" if is_windows else f"which {command}"
    try:
        result = subprocess.run(
            shell_cmd,
            shell=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        # where.exe may return multiple lines; return the first one
        first = result.stdout.strip().splitlines()[0]
        return first or None
    except OSError:
        return None


async def _which_subprocess_async(command: str) -> Optional[str]:
    """Async subprocess fallback (mirrors TS whichNodeAsync)."""
    is_windows = platform.system() == "Windows"
    shell_cmd = f"where.exe {command}" if is_windows else f"which {command}"
    try:
        proc = await asyncio.create_subprocess_shell(
            shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode != 0 or not stdout:
            return None
        first = stdout.decode().strip().splitlines()[0]
        return first or None
    except OSError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def which_sync(command: str) -> Optional[str]:
    """
    Return the full path to *command*, or ``None`` if not found.

    Uses ``shutil.which`` (stdlib, no subprocess).
    """
    return _which_shutil(command)


async def which(command: str) -> Optional[str]:
    """
    Async version of :func:`which_sync`.

    Uses ``shutil.which`` directly (no subprocess needed); the async
    wrapper exists for API compatibility with callers that await it.
    """
    result = _which_shutil(command)
    if result is not None:
        return result
    # Fallback to subprocess for edge cases (e.g., PATH not yet updated)
    return await _which_subprocess_async(command)

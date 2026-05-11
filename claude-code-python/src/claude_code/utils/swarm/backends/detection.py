"""
Backend detection utilities.

Port of utils/swarm/backends/detection.ts
"""

from __future__ import annotations

import asyncio
import os
from typing import Optional

# ---------------------------------------------------------------------------
# Module-level constants (captured at import time, like the TS module)
# ---------------------------------------------------------------------------

# Captured at module load time to detect if Claude was started from within tmux.
# Shell code may override TMUX env var later, so we capture the original value.
_ORIGINAL_USER_TMUX: Optional[str] = os.environ.get("TMUX")

# Captured at module load time to get the leader's tmux pane ID.
# TMUX_PANE is set by tmux (e.g., %0, %1) when a process runs inside tmux.
_ORIGINAL_TMUX_PANE: Optional[str] = os.environ.get("TMUX_PANE")

# The it2 CLI command name.
IT2_COMMAND = "it2"

# Tmux command name (mirrors constants.ts TMUX_COMMAND)
_TMUX_COMMAND = "tmux"

# ---------------------------------------------------------------------------
# Caches
# ---------------------------------------------------------------------------

_is_inside_tmux_cached: Optional[bool] = None
_is_in_i_term2_cached: Optional[bool] = None


# ---------------------------------------------------------------------------
# Synchronous helpers
# ---------------------------------------------------------------------------


def is_inside_tmux_sync() -> bool:
    """
    Checks if we're running inside a tmux session (synchronous version).
    Uses the original TMUX value captured at module load.

    IMPORTANT: Only checks TMUX env var — does NOT run `tmux display-message`
    because that succeeds if ANY tmux server is running, not just if THIS
    process is inside tmux.
    """
    return bool(_ORIGINAL_USER_TMUX)


def get_leader_pane_id() -> Optional[str]:
    """
    Gets the leader's tmux pane ID captured at module load.
    Returns None if not running inside tmux.
    """
    return _ORIGINAL_TMUX_PANE or None


def is_in_i_term2() -> bool:
    """
    Checks if we're currently running inside iTerm2.

    Uses multiple detection methods:
    1. TERM_PROGRAM env var set to "iTerm.app"
    2. ITERM_SESSION_ID env var is present
    3. env.terminal detection (mirrors utils/env.ts)

    Caches the result since this won't change during the process lifetime.
    """
    global _is_in_i_term2_cached
    if _is_in_i_term2_cached is not None:
        return _is_in_i_term2_cached

    term_program = os.environ.get("TERM_PROGRAM", "")
    has_iterm_session_id = bool(os.environ.get("ITERM_SESSION_ID"))

    _is_in_i_term2_cached = (
        term_program == "iTerm.app" or has_iterm_session_id
    )
    return _is_in_i_term2_cached


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


async def is_inside_tmux() -> bool:
    """
    Checks if we're currently running inside a tmux session (async version).
    Caches the result since this won't change during the process lifetime.

    IMPORTANT: Only checks TMUX env var — does NOT run `tmux display-message`.
    """
    global _is_inside_tmux_cached
    if _is_inside_tmux_cached is not None:
        return _is_inside_tmux_cached

    _is_inside_tmux_cached = bool(_ORIGINAL_USER_TMUX)
    return _is_inside_tmux_cached


async def _exec_file_no_throw(cmd: str, args: list[str]) -> tuple[str, str, int]:
    """Run a subprocess and return (stdout, stderr, code). Never raises."""
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        return (
            stdout_b.decode(errors="replace"),
            stderr_b.decode(errors="replace"),
            proc.returncode or 0,
        )
    except Exception:
        return ("", "", 1)


async def is_tmux_available() -> bool:
    """Checks if tmux is available on the system (installed and in PATH)."""
    _, _, code = await _exec_file_no_throw(_TMUX_COMMAND, ["-V"])
    return code == 0


async def is_it2_cli_available() -> bool:
    """
    Checks if the it2 CLI tool is available AND can reach the iTerm2 Python API.
    Uses 'session list' (not '--version') because --version succeeds even when
    the Python API is disabled in iTerm2 preferences.
    """
    _, _, code = await _exec_file_no_throw(IT2_COMMAND, ["session", "list"])
    return code == 0


# ---------------------------------------------------------------------------
# Reset (for testing)
# ---------------------------------------------------------------------------


def reset_detection_cache() -> None:
    """Resets all cached detection results. Used for testing."""
    global _is_inside_tmux_cached, _is_in_i_term2_cached
    _is_inside_tmux_cached = None
    _is_in_i_term2_cached = None

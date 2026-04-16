# 原始 TS: services/preventSleep.ts
"""Prevent the OS from sleeping while Claude is working.

On macOS uses `caffeinate`. No-op on other platforms.
"""
from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
from typing import Optional

logger = logging.getLogger(__name__)

CAFFEINATE_TIMEOUT_SECONDS = 300  # 5 minutes
RESTART_INTERVAL_SECONDS = 4 * 60  # restart before timeout expires

_caffeinate_proc: Optional[subprocess.Popen] = None  # type: ignore[type-arg]
_restart_task: asyncio.Task | None = None
_ref_count = 0


def start_prevent_sleep() -> None:
    """Increment ref-count and start sleep prevention if not already active."""
    global _ref_count  # noqa: PLW0603
    _ref_count += 1
    if _ref_count == 1:
        _spawn_caffeinate()


def stop_prevent_sleep() -> None:
    """Decrement ref-count; stop sleep prevention when count reaches zero."""
    global _ref_count  # noqa: PLW0603
    if _ref_count > 0:
        _ref_count -= 1
    if _ref_count == 0:
        _kill_caffeinate()


def _spawn_caffeinate() -> None:
    global _caffeinate_proc  # noqa: PLW0603
    if platform.system() != "Darwin":
        return
    try:
        _caffeinate_proc = subprocess.Popen(
            ["caffeinate", "-i", "-t", str(CAFFEINATE_TIMEOUT_SECONDS)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        logger.debug("caffeinate started (pid=%d)", _caffeinate_proc.pid)
    except FileNotFoundError:
        logger.debug("caffeinate not found")


def _kill_caffeinate() -> None:
    global _caffeinate_proc  # noqa: PLW0603
    if _caffeinate_proc and _caffeinate_proc.poll() is None:
        _caffeinate_proc.terminate()
        logger.debug("caffeinate stopped")
    _caffeinate_proc = None

"""
Consolidation lock for auto-dream background memory consolidation.
Ported from services/autoDream/consolidationLock.ts

Lock file whose mtime IS lastConsolidatedAt. Body is the holder's PID.
Lives inside the memory dir so it keys on git-root like memory does.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

LOCK_FILE = ".consolidate-lock"

# Stale past this even if the PID is live (PID reuse guard)
HOLDER_STALE_MS = 60 * 60 * 1000  # 1 hour in milliseconds


def _get_auto_mem_path() -> str:
    """
    Get the auto-memory path. In real impl this reads from settings/env.
    Falls back to ~/.claude/memory.
    """
    return os.environ.get(
        "CLAUDE_CODE_AUTO_MEM_PATH",
        str(Path.home() / ".claude" / "memory"),
    )


def _lock_path() -> Path:
    return Path(_get_auto_mem_path()) / LOCK_FILE


def _is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


async def read_last_consolidated_at() -> float:
    """
    Return the mtime of the lock file as lastConsolidatedAt.
    Returns 0.0 if absent.
    Per-turn cost: one stat.
    """
    path = _lock_path()
    try:
        stat = path.stat()
        return stat.st_mtime * 1000  # return milliseconds, like JS Date.now()
    except FileNotFoundError:
        return 0.0


async def try_acquire_consolidation_lock() -> Optional[float]:
    """
    Acquire the consolidation lock.

    Writes current PID to lock file with mtime = now.
    Returns the pre-acquire mtime (for rollback), or None if blocked / lost a race.

      Success → do nothing; mtime stays at now.
      Failure → rollback_consolidation_lock(prior_mtime) rewinds mtime.
      Crash   → mtime stuck, dead PID → next process reclaims.
    """
    path = _lock_path()

    mtime_ms: Optional[float] = None
    holder_pid: Optional[int] = None

    try:
        stat = path.stat()
        mtime_ms = stat.st_mtime * 1000
        content = path.read_text(encoding="utf-8").strip()
        parsed = int(content)
        if parsed > 0:
            holder_pid = parsed
    except (FileNotFoundError, ValueError):
        pass  # ENOENT or unparseable body

    # Check if an active holder is still running
    if mtime_ms is not None and (time.time() * 1000 - mtime_ms) < HOLDER_STALE_MS:
        if holder_pid is not None and _is_process_running(holder_pid):
            logger.debug(
                "[autoDream] lock held by live PID %d (mtime %ds ago)",
                holder_pid,
                int((time.time() * 1000 - mtime_ms) / 1000),
            )
            return None
        # Dead PID or unparseable body — reclaim

    # Memory dir may not exist yet
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(os.getpid()), encoding="utf-8")

    # Two reclaimers both write → last wins the PID. Loser bails on re-read.
    try:
        verify = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None

    try:
        if int(verify) != os.getpid():
            return None
    except ValueError:
        return None

    return mtime_ms if mtime_ms is not None else 0.0


async def rollback_consolidation_lock(prior_mtime: float) -> None:
    """
    Rewind mtime to pre-acquire after a failed fork.
    Clears the PID body — otherwise our still-running process would look
    like it's holding. prior_mtime 0 → unlink (restore no-file state).
    """
    path = _lock_path()
    try:
        if prior_mtime == 0:
            path.unlink(missing_ok=True)
            return
        path.write_text("", encoding="utf-8")
        t = prior_mtime / 1000.0  # convert ms → seconds for os.utime
        os.utime(path, (t, t))
    except Exception as exc:
        logger.debug(
            "[autoDream] rollback failed: %s — next trigger delayed to minHours",
            exc,
        )


async def list_sessions_touched_since(since_ms: float) -> list[str]:
    """
    Return session IDs with mtime after since_ms.
    Uses mtime (sessions TOUCHED since), not birthtime.
    Caller excludes the current session.
    """
    from pathlib import Path as _Path

    original_cwd = os.environ.get("CLAUDE_CODE_CWD", os.getcwd())
    project_key = original_cwd.replace("/", "_").lstrip("_")
    transcript_dir = _Path.home() / ".claude" / "projects" / project_key

    if not transcript_dir.exists():
        return []

    session_ids: list[str] = []
    try:
        for entry in transcript_dir.iterdir():
            if not entry.name.endswith(".jsonl"):
                continue
            # Extract session ID from filename (UUID format)
            stem = entry.stem
            import re
            if not re.match(
                r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
                stem,
            ):
                continue
            stat = entry.stat()
            if stat.st_mtime * 1000 > since_ms:
                session_ids.append(stem)
    except OSError as exc:
        logger.debug("[autoDream] listSessionsTouchedSince error: %s", exc)

    return session_ids


async def record_consolidation() -> None:
    """
    Stamp from manual /dream. Optimistic — fires at prompt-build time.
    Best-effort.
    """
    path = _lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(os.getpid()), encoding="utf-8")
    except Exception as exc:
        logger.debug("[autoDream] recordConsolidation write failed: %s", exc)

"""
Scheduler lease lock for .claude/scheduled_tasks.lock.

When multiple Claude sessions run in the same project directory, only one
should drive the cron scheduler. The first session to acquire this lock
becomes the scheduler; others stay passive and periodically probe the lock.
If the owner dies (PID no longer running), a passive session takes over.

Pattern: O_EXCL atomic create, PID liveness probe, stale-lock recovery,
cleanup-on-exit.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

LOCK_FILE_REL = os.path.join(".claude", "scheduled_tasks.lock")


@dataclass
class SchedulerLock:
    session_id: str
    pid: int
    acquired_at: float


def _get_lock_path(directory: Optional[str] = None) -> Path:
    base = directory or os.getcwd()
    return Path(base) / LOCK_FILE_REL


def _is_process_running(pid: int) -> bool:
    """Check if a process with the given PID is running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _read_lock(directory: Optional[str] = None) -> Optional[SchedulerLock]:
    """Read the lock file and return parsed SchedulerLock, or None on failure."""
    path = _get_lock_path(directory)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        return SchedulerLock(
            session_id=str(data["sessionId"]),
            pid=int(data["pid"]),
            acquired_at=float(data["acquiredAt"]),
        )
    except Exception:
        return None


def _write_lock_data(lock: SchedulerLock, path: Path) -> None:
    payload = json.dumps(
        {"sessionId": lock.session_id, "pid": lock.pid, "acquiredAt": lock.acquired_at}
    )
    path.write_text(payload, encoding="utf-8")


def _try_create_exclusive(lock: SchedulerLock, directory: Optional[str] = None) -> bool:
    """Atomically create the lock file (O_EXCL). Returns True on success."""
    path = _get_lock_path(directory)
    payload = json.dumps(
        {"sessionId": lock.session_id, "pid": lock.pid, "acquiredAt": lock.acquired_at}
    )
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(payload)
        return True
    except FileExistsError:
        return False
    except FileNotFoundError:
        # Directory doesn't exist yet — create and retry once
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            with os.fdopen(fd, "w") as f:
                f.write(payload)
            return True
        except FileExistsError:
            return False


class CronTaskLock:
    """
    Scheduler lock that prevents concurrent cron task execution across sessions.

    Usage::

        lock = CronTaskLock(session_id="my-session", directory="/path/to/project")
        acquired = await lock.acquire()
        if acquired:
            try:
                # do scheduler work
                ...
            finally:
                await lock.release()
    """

    def __init__(
        self,
        session_id: str,
        directory: Optional[str] = None,
    ) -> None:
        self.session_id = session_id
        self.directory = directory
        self._last_blocked_by: Optional[str] = None
        self._in_memory_lock = asyncio.Lock()

    def is_locked(self) -> bool:
        """Return True if lock file exists (regardless of owner)."""
        return _get_lock_path(self.directory).exists()

    async def acquire(self) -> bool:
        """
        Try to acquire the scheduler lock.

        Returns True on success, False if another live session holds it.

        - Already ours → True (idempotent re-acquire, updates PID if changed)
        - Another live PID → False
        - Stale (PID dead / corrupt) → unlink and retry exclusive create once
        """
        async with self._in_memory_lock:
            lock = SchedulerLock(
                session_id=self.session_id,
                pid=os.getpid(),
                acquired_at=time.time() * 1000,  # ms like JS Date.now()
            )

            if _try_create_exclusive(lock, self.directory):
                self._last_blocked_by = None
                return True

            existing = _read_lock(self.directory)

            # Already ours (idempotent). Update PID if process restarted.
            if existing and existing.session_id == self.session_id:
                if existing.pid != os.getpid():
                    _write_lock_data(lock, _get_lock_path(self.directory))
                return True

            # Another live session holds it
            if existing and _is_process_running(existing.pid):
                self._last_blocked_by = existing.session_id
                return False

            # Stale lock — unlink and retry
            try:
                _get_lock_path(self.directory).unlink()
            except FileNotFoundError:
                pass

            if _try_create_exclusive(lock, self.directory):
                self._last_blocked_by = None
                return True

            # Another session won the recovery race
            return False

    async def release(self) -> None:
        """Release the lock if the current session owns it."""
        existing = _read_lock(self.directory)
        if not existing or existing.session_id != self.session_id:
            return
        try:
            _get_lock_path(self.directory).unlink()
        except FileNotFoundError:
            pass

    async def __aenter__(self) -> "CronTaskLock":
        await self.acquire()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.release()


# Module-level convenience functions mirroring the TS exports

async def try_acquire_scheduler_lock(
    directory: Optional[str] = None,
    session_id: Optional[str] = None,
) -> bool:
    """Try to acquire the scheduler lock for the current session."""
    sid = session_id or f"session-{os.getpid()}"
    lock = CronTaskLock(session_id=sid, directory=directory)
    return await lock.acquire()


async def release_scheduler_lock(
    directory: Optional[str] = None,
    session_id: Optional[str] = None,
) -> None:
    """Release the scheduler lock if the current session owns it."""
    sid = session_id or f"session-{os.getpid()}"
    lock = CronTaskLock(session_id=sid, directory=directory)
    await lock.release()

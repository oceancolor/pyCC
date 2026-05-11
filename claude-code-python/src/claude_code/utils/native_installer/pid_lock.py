"""
PID-Based Version Locking

This module provides PID-based locking for running Claude Code versions.
Unlike mtime-based locking (which can hold locks for 30 days after a crash),
PID-based locking can immediately detect when a process is no longer running.

Lock files contain JSON with the PID and metadata, and staleness is determined
by checking if the process is still alive.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

# Fallback stale timeout (2 hours) - used when PID check is inconclusive
FALLBACK_STALE_MS = 2 * 60 * 60 * 1000  # 2 hours in milliseconds


def is_pid_based_locking_enabled() -> bool:
    """
    Check if PID-based version locking is enabled.
    When disabled, falls back to mtime-based locking (30-day timeout).
    """
    env_var = os.environ.get("ENABLE_PID_BASED_VERSION_LOCKING", "")
    if env_var.lower() in ("true", "1", "yes"):
        return True
    if env_var.lower() in ("false", "0", "no"):
        return False
    # Default: enabled
    return True


@dataclass
class VersionLockContent:
    """Content stored in a version lock file."""
    pid: int
    version: str
    exec_path: str
    acquired_at: int  # timestamp when lock was acquired


@dataclass
class LockInfo:
    """Information about a lock for diagnostic purposes."""
    version: str
    pid: int
    is_process_running: bool
    exec_path: str
    acquired_at: float  # Unix timestamp
    lock_file_path: str


def is_process_running(pid: int) -> bool:
    """
    Check if a process with the given PID is currently running.
    Uses signal 0 which doesn't actually send a signal but checks if the
    process exists.
    """
    # PID 0 is special; PID 1 is init/systemd, always running but not for locks
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _get_process_command(pid: int) -> Optional[str]:
    """Get the command line of a process by PID."""
    try:
        # Try /proc/PID/cmdline on Linux
        cmdline_path = f"/proc/{pid}/cmdline"
        if os.path.exists(cmdline_path):
            with open(cmdline_path, "rb") as f:
                data = f.read()
            return data.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    except Exception:
        pass

    try:
        # Fall back to ps
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass

    return None


def _is_claude_process(pid: int, expected_exec_path: str) -> bool:
    """
    Validate that a running process is actually a Claude process.
    This helps mitigate PID reuse issues.
    """
    if not is_process_running(pid):
        return False

    # If PID matches our current process, we know it's valid
    if pid == os.getpid():
        return True

    try:
        command = _get_process_command(pid)
        if not command:
            # If we can't get the command, trust the PID check
            return True

        normalized_command = command.lower()
        normalized_exec_path = expected_exec_path.lower()

        return "claude" in normalized_command or normalized_exec_path in normalized_command
    except Exception:
        return True


def read_lock_content(lock_file_path: str) -> Optional[VersionLockContent]:
    """Read and parse a lock file's content."""
    try:
        with open(lock_file_path, "r", encoding="utf-8") as f:
            content = f.read()

        if not content or not content.strip():
            return None

        parsed = json.loads(content)

        # Validate required fields
        if not isinstance(parsed.get("pid"), int):
            return None
        if not parsed.get("version"):
            return None
        if not parsed.get("execPath"):
            return None

        return VersionLockContent(
            pid=parsed["pid"],
            version=parsed["version"],
            exec_path=parsed["execPath"],
            acquired_at=parsed.get("acquiredAt", 0),
        )
    except Exception:
        return None


def is_lock_active(lock_file_path: str) -> bool:
    """Check if a lock file represents an active lock (process still running)."""
    content = read_lock_content(lock_file_path)

    if not content:
        return False

    pid = content.pid
    exec_path = content.exec_path

    # Primary check: is the process running?
    if not is_process_running(pid):
        return False

    # Secondary validation: is it actually a Claude process?
    if not _is_claude_process(pid, exec_path):
        logger.debug(
            "Lock PID %d is running but does not appear to be Claude - treating as stale",
            pid,
        )
        return False

    # Fallback: if the lock is very old (> 2 hours) double-check
    try:
        stats = os.stat(lock_file_path)
        age_ms = (time.time() - stats.st_mtime) * 1000
        if age_ms > FALLBACK_STALE_MS:
            if not is_process_running(pid):
                return False
    except Exception:
        pass

    return True


def _write_lock_file(lock_file_path: str, content: VersionLockContent) -> None:
    """Write lock content to a file atomically."""
    temp_path = f"{lock_file_path}.tmp.{os.getpid()}.{int(time.time() * 1000)}"

    data = json.dumps(
        {
            "pid": content.pid,
            "version": content.version,
            "execPath": content.exec_path,
            "acquiredAt": content.acquired_at,
        },
        indent=2,
    )

    try:
        with open(temp_path, "w", encoding="utf-8") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.rename(temp_path, lock_file_path)
    except Exception:
        # Clean up temp file on failure (best-effort)
        try:
            os.unlink(temp_path)
        except Exception:
            pass
        raise


async def try_acquire_lock(
    version_path: str,
    lock_file_path: str,
) -> Optional[Callable[[], None]]:
    """
    Try to acquire a lock on a version file.
    Returns a release function if successful, None if the lock is already held.
    """
    version_name = os.path.basename(version_path)

    # Check if there's an existing active lock
    if is_lock_active(lock_file_path):
        existing_content = read_lock_content(lock_file_path)
        logger.debug(
            "Cannot acquire lock for %s - held by PID %s",
            version_name,
            existing_content.pid if existing_content else "unknown",
        )
        return None

    # Try to acquire the lock
    lock_content = VersionLockContent(
        pid=os.getpid(),
        version=version_name,
        exec_path=os.path.realpath(os.sys.executable),  # type: ignore[attr-defined]
        acquired_at=int(time.time() * 1000),
    )

    try:
        _write_lock_file(lock_file_path, lock_content)

        # Verify we actually got the lock (race condition check)
        verify_content = read_lock_content(lock_file_path)
        if verify_content is None or verify_content.pid != os.getpid():
            # Another process won the race
            return None

        logger.debug("Acquired PID lock for %s (PID %d)", version_name, os.getpid())

        def release() -> None:
            try:
                current_content = read_lock_content(lock_file_path)
                if current_content and current_content.pid == os.getpid():
                    os.unlink(lock_file_path)
                    logger.debug("Released PID lock for %s", version_name)
            except Exception as e:
                logger.debug("Failed to release lock for %s: %s", version_name, e)

        return release
    except Exception as e:
        logger.debug("Failed to acquire lock for %s: %s", version_name, e)
        return None


async def acquire_process_lifetime_lock(
    version_path: str,
    lock_file_path: str,
) -> bool:
    """
    Acquire a lock and hold it for the lifetime of the process.
    This is used for locking the currently running version.
    """
    release = await try_acquire_lock(version_path, lock_file_path)

    if release is None:
        return False

    # Register cleanup on process exit
    import atexit
    import signal as _signal

    def cleanup() -> None:
        try:
            release()
        except Exception:
            pass

    atexit.register(cleanup)

    # Register signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            _signal.signal(sig, lambda s, f: cleanup())
        except Exception:
            pass

    # Don't call release() - we want to hold the lock until process exits
    return True


async def with_lock(
    version_path: str,
    lock_file_path: str,
    callback: Callable,
) -> bool:
    """
    Execute a callback while holding a lock.
    Returns True if the callback executed, False if lock couldn't be acquired.
    """
    release = await try_acquire_lock(version_path, lock_file_path)

    if release is None:
        return False

    try:
        result = callback()
        if asyncio.iscoroutine(result):
            await result
        return True
    finally:
        release()


def get_all_lock_info(locks_dir: str) -> list[LockInfo]:
    """Get information about all version locks for diagnostics."""
    lock_infos: list[LockInfo] = []

    try:
        lock_dir = Path(locks_dir)
        if not lock_dir.exists():
            return lock_infos

        for lock_file in lock_dir.iterdir():
            if not lock_file.name.endswith(".lock"):
                continue

            lock_file_path = str(lock_file)
            content = read_lock_content(lock_file_path)

            if content:
                lock_infos.append(
                    LockInfo(
                        version=content.version,
                        pid=content.pid,
                        is_process_running=is_process_running(content.pid),
                        exec_path=content.exec_path,
                        acquired_at=content.acquired_at / 1000.0,
                        lock_file_path=lock_file_path,
                    )
                )
    except FileNotFoundError:
        return lock_infos
    except Exception as e:
        logger.error("Error getting lock info: %s", e)

    return lock_infos


def cleanup_stale_locks(locks_dir: str) -> int:
    """
    Clean up stale locks (locks where the process is no longer running).
    Returns the number of locks cleaned up.
    """
    import shutil

    lock_dir = Path(locks_dir)
    cleaned_count = 0

    try:
        if not lock_dir.exists():
            return 0

        for lock_entry in lock_dir.iterdir():
            if not lock_entry.name.endswith(".lock"):
                continue

            lock_file_path = str(lock_entry)

            try:
                if lock_entry.is_dir():
                    # Legacy directory lock - remove when PID-based locking is enabled
                    shutil.rmtree(lock_file_path, ignore_errors=True)
                    cleaned_count += 1
                    logger.debug("Cleaned up legacy directory lock: %s", lock_entry.name)
                elif not is_lock_active(lock_file_path):
                    # PID-based file lock with no running process
                    os.unlink(lock_file_path)
                    cleaned_count += 1
                    logger.debug("Cleaned up stale lock: %s", lock_entry.name)
            except Exception:
                # Ignore individual cleanup errors
                pass
    except FileNotFoundError:
        return 0
    except Exception as e:
        logger.error("Error cleaning up stale locks: %s", e)

    return cleaned_count

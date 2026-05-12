"""
computer_use_lock.py - File-based lock for computer use sessions.

Port of TypeScript computerUseLock.ts.
"""

import asyncio
import json
import os
import signal
from pathlib import Path
from typing import Callable, Optional, Union

LOCK_FILENAME = 'computer-use.lock'

# Holds the unregister function for the shutdown cleanup handler
_unregister_cleanup: Optional[Callable] = None


class ComputerUseLock:
    """Lock file data."""
    def __init__(self, session_id: str, pid: int, acquired_at: int):
        self.session_id = session_id
        self.pid = pid
        self.acquired_at = acquired_at

    def to_dict(self) -> dict:
        return {
            'sessionId': self.session_id,
            'pid': self.pid,
            'acquiredAt': self.acquired_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Optional['ComputerUseLock']:
        if not isinstance(data, dict):
            return None
        session_id = data.get('sessionId')
        pid = data.get('pid')
        if not isinstance(session_id, str) or not isinstance(pid, int):
            return None
        return cls(
            session_id=session_id,
            pid=pid,
            acquired_at=data.get('acquiredAt', 0),
        )


def _get_lock_path() -> Path:
    """Get the path to the lock file."""
    from ...utils.env_utils import get_claude_config_home_dir
    return Path(get_claude_config_home_dir()) / LOCK_FILENAME


def _read_lock() -> Optional[ComputerUseLock]:
    """Read the current lock file."""
    try:
        lock_path = _get_lock_path()
        data = json.loads(lock_path.read_text('utf-8'))
        return ComputerUseLock.from_dict(data)
    except Exception:
        return None


def _is_process_running(pid: int) -> bool:
    """Check whether a process is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except Exception:
        return False


def _try_create_exclusive(lock: ComputerUseLock) -> bool:
    """Attempt to create the lock file atomically."""
    lock_path = _get_lock_path()
    try:
        # O_CREAT | O_EXCL equivalent
        fd = os.open(str(lock_path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            os.write(fd, json.dumps(lock.to_dict()).encode('utf-8'))
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        return False
    except Exception:
        raise


def _register_lock_cleanup() -> None:
    """Register a shutdown cleanup handler."""
    global _unregister_cleanup
    if _unregister_cleanup:
        _unregister_cleanup()

    def cleanup() -> None:
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            loop.run_until_complete(release_computer_use_lock())
            loop.close()
        except Exception:
            pass

    try:
        from ...utils.cleanup_registry import register_cleanup
        unregister = register_cleanup(cleanup)
        _unregister_cleanup = unregister
    except ImportError:
        import atexit
        atexit.register(cleanup)
        _unregister_cleanup = lambda: None  # noqa: E731


async def check_computer_use_lock() -> dict:
    """
    Check lock state without acquiring.

    Returns:
        dict with 'kind' key: 'free', 'held_by_self', or 'blocked'
    """
    from ...bootstrap.state import get_session_id

    existing = _read_lock()
    if not existing:
        return {'kind': 'free'}
    if existing.session_id == get_session_id():
        return {'kind': 'held_by_self'}
    if _is_process_running(existing.pid):
        return {'kind': 'blocked', 'by': existing.session_id}

    # Stale lock recovery
    try:
        _get_lock_path().unlink()
    except Exception:
        pass
    return {'kind': 'free'}


def is_lock_held_locally() -> bool:
    """Zero-syscall check: does THIS process believe it holds the lock?"""
    return _unregister_cleanup is not None


async def try_acquire_computer_use_lock() -> dict:
    """
    Try to acquire the computer-use lock for the current session.

    Returns:
        dict with 'kind' key: 'acquired' (with 'fresh' bool) or 'blocked' (with 'by' str)
    """
    from ...bootstrap.state import get_session_id
    import time

    session_id = get_session_id()
    lock = ComputerUseLock(
        session_id=session_id,
        pid=os.getpid(),
        acquired_at=int(time.time() * 1000),
    )

    lock_dir = _get_lock_path().parent
    lock_dir.mkdir(parents=True, exist_ok=True)

    # Fresh acquisition
    if _try_create_exclusive(lock):
        _register_lock_cleanup()
        return {'kind': 'acquired', 'fresh': True}

    existing = _read_lock()

    if not existing:
        try:
            _get_lock_path().unlink()
        except Exception:
            pass
        if _try_create_exclusive(lock):
            _register_lock_cleanup()
            return {'kind': 'acquired', 'fresh': True}
        existing2 = _read_lock()
        return {'kind': 'blocked', 'by': existing2.session_id if existing2 else 'unknown'}

    if existing.session_id == session_id:
        return {'kind': 'acquired', 'fresh': False}

    if _is_process_running(existing.pid):
        return {'kind': 'blocked', 'by': existing.session_id}

    # Stale lock recovery
    try:
        _get_lock_path().unlink()
    except Exception:
        pass
    if _try_create_exclusive(lock):
        _register_lock_cleanup()
        return {'kind': 'acquired', 'fresh': True}
    existing3 = _read_lock()
    return {'kind': 'blocked', 'by': existing3.session_id if existing3 else 'unknown'}


async def release_computer_use_lock() -> bool:
    """
    Release the computer-use lock if the current session owns it.

    Returns:
        True if we actually released the lock, False otherwise.
    """
    global _unregister_cleanup
    from ...bootstrap.state import get_session_id

    if _unregister_cleanup:
        _unregister_cleanup()
    _unregister_cleanup = None

    existing = _read_lock()
    if not existing or existing.session_id != get_session_id():
        return False

    try:
        _get_lock_path().unlink()
        return True
    except Exception:
        return False

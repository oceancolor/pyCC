"""
File locking utilities. Ported from lockfile.ts
Uses fcntl-based locking or filelock library.
"""
from __future__ import annotations
import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional


async def lock(file: str, timeout: float = 30.0) -> "FileLock":
    lk = FileLock(file)
    await lk.acquire(timeout=timeout)
    return lk


def lock_sync(file: str) -> "FileLock":
    lk = FileLock(file)
    lk.acquire_sync()
    return lk


async def unlock(file: str) -> None:
    FileLock(file).release_sync()


async def check(file: str) -> bool:
    """Return True if file is currently locked."""
    try:
        import fcntl
        fd = os.open(file, os.O_RDONLY | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(fd, fcntl.LOCK_UN)
            return False
        except OSError:
            return True
        finally:
            os.close(fd)
    except Exception:
        return False


class FileLock:
    def __init__(self, path: str) -> None:
        self.path = path
        self._fd: Optional[int] = None

    async def acquire(self, timeout: float = 30.0) -> None:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: self.acquire_sync(timeout))

    def acquire_sync(self, timeout: float = 30.0) -> None:
        import fcntl, time
        self._fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o644)
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"Could not acquire lock on {self.path}")
                time.sleep(0.05)

    def release_sync(self) -> None:
        if self._fd is not None:
            try:
                import fcntl
                fcntl.flock(self._fd, fcntl.LOCK_UN)
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None

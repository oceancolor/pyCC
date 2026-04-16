"""
exec_file_no_throw_portable.py - Cross-platform subprocess execution without exceptions.

Ported from execFileNoThrowPortable.ts (which in the source is actually
execSyncWithDefaults_DEPRECATED / execaSync wrapper).

Provides:
  exec_sync(command, *, timeout_ms, input_data, capture_stderr)
    → str | None   (stdout trimmed, None on error / empty output)

This is the Python equivalent of execSyncWithDefaults_DEPRECATED — a
synchronous shell executor that never raises on non-zero exit codes.

Note: Sync subprocess calls block the event loop; prefer asyncio.create_subprocess_shell
for async contexts.  This module exists for compatibility with callers that
need a blocking call (e.g., git metadata during startup).
"""

from __future__ import annotations

import subprocess
import threading
from typing import Optional

# Default timeout: 10 minutes (matching TS constant)
_DEFAULT_TIMEOUT_MS = 10 * 60 * 1_000


def exec_sync(
    command: str,
    *,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    input_data: Optional[str] = None,
    capture_stderr: bool = False,
    abort_event: Optional[threading.Event] = None,
) -> Optional[str]:
    """
    Execute *command* in a shell synchronously.

    Returns:
        Stripped stdout as ``str``, or ``None`` if the command fails,
        exits non-zero, or produces no output.

    Args:
        command:        Shell command string.
        timeout_ms:     Timeout in milliseconds (default 10 min).
        input_data:     Optional string piped to stdin.
        capture_stderr: If True, stderr is captured (and discarded); otherwise
                        it is inherited from the parent process.
        abort_event:    A ``threading.Event``; if set before the call starts,
                        returns ``None`` immediately (mirrors AbortSignal.throwIfAborted).
    """
    if abort_event is not None and abort_event.is_set():
        return None

    timeout_sec = timeout_ms / 1000.0
    stderr_dest = subprocess.PIPE if capture_stderr else subprocess.DEVNULL

    try:
        result = subprocess.run(
            command,
            shell=True,
            text=True,
            stdin=subprocess.PIPE if input_data is not None else subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=stderr_dest,
            timeout=timeout_sec,
            input=input_data,
        )
        if result.returncode != 0 or not result.stdout:
            return None
        stripped = result.stdout.strip()
        return stripped if stripped else None
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return None


async def exec_async(
    command: str,
    *,
    timeout_ms: int = _DEFAULT_TIMEOUT_MS,
    input_data: Optional[str] = None,
) -> Optional[str]:
    """
    Async variant of exec_sync using asyncio subprocesses.
    Preferred in async contexts to avoid blocking the event loop.
    """
    import asyncio

    timeout_sec = timeout_ms / 1000.0
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdin=asyncio.subprocess.PIPE if input_data is not None else asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdin_bytes = input_data.encode() if input_data else None
        stdout, _ = await asyncio.wait_for(
            proc.communicate(input=stdin_bytes), timeout=timeout_sec
        )
        if proc.returncode != 0 or not stdout:
            return None
        stripped = stdout.decode().strip()
        return stripped if stripped else None
    except (asyncio.TimeoutError, OSError):
        return None

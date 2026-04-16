"""
Generic process utilities — start / kill / probe subprocesses.

Mirrors the platform-agnostic helpers in genericProcessUtils.ts.
Uses asyncio.subprocess for non-blocking process management.
"""

from __future__ import annotations

import asyncio
import os
import platform
import signal
import subprocess
from typing import Sequence


# ---------------------------------------------------------------------------
# Synchronous probe
# ---------------------------------------------------------------------------

def is_process_running(pid: int) -> bool:
    """Return True if a process with *pid* is alive.

    PID ≤ 1 always returns False (0 = current process group, 1 = init).
    Sends signal 0 (existence probe) — does *not* kill the process.
    On EPERM (process exists but owned by another user) returns False,
    matching the conservative TS behaviour for lock recovery.
    """
    if pid <= 1:
        return False
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        # EPERM: process exists but we don't own it → treat as not running
        return False
    except (ProcessLookupError, OSError):
        return False


# ---------------------------------------------------------------------------
# Async run / kill
# ---------------------------------------------------------------------------

async def run_process(
    cmd: Sequence[str],
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: float | None = None,
) -> tuple[int, str, str]:
    """Start *cmd* as a subprocess and wait for it to finish.

    Args:
        cmd:     Command and arguments (list form; first element is the executable).
        cwd:     Working directory for the child process.
        env:     Environment mapping; defaults to the current process environment.
        timeout: Optional wall-clock timeout in seconds. On expiry the process is
                 killed and ``asyncio.TimeoutError`` is raised.

    Returns:
        ``(return_code, stdout, stderr)`` — all text decoded as UTF-8.
    """
    merged_env: dict[str, str] | None = None
    if env is not None:
        merged_env = {**os.environ, **env}

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=cwd,
        env=merged_env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except ProcessLookupError:
            pass
        await proc.wait()
        raise

    returncode: int = proc.returncode if proc.returncode is not None else -1
    return returncode, stdout_bytes.decode("utf-8", errors="replace"), stderr_bytes.decode("utf-8", errors="replace")


async def kill_process(pid: int, force: bool = False) -> bool:
    """Send a termination signal to *pid*.

    On Unix sends SIGTERM by default, or SIGKILL when *force* is True.
    On Windows calls ``taskkill /F`` (force-kill) regardless of *force*.

    Returns True if the signal was delivered, False if the process was
    not found.
    """
    if pid <= 1:
        return False

    if platform.system() == "Windows":
        try:
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/F"],
                capture_output=True,
                timeout=5,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    sig = signal.SIGKILL if force else signal.SIGTERM
    try:
        os.kill(pid, sig)
        return True
    except (ProcessLookupError, OSError):
        return False


# ---------------------------------------------------------------------------
# Ancestor / child helpers (mirrors getAncestorPidsAsync / getChildPids)
# ---------------------------------------------------------------------------

async def get_ancestor_pids(pid: int, max_depth: int = 10) -> list[int]:
    """Return the chain of ancestor PIDs from immediate parent upward."""
    if platform.system() == "Windows":
        script = (
            f"$p={pid}; $a=@(); "
            f"for($i=0;$i<{max_depth};$i++){{"
            "$pr=Get-CimInstance Win32_Process -Filter \"ProcessId=$p\" "
            "-ErrorAction SilentlyContinue; "
            "if(-not $pr -or -not $pr.ParentProcessId -or $pr.ParentProcessId -eq 0){break}; "
            "$p=$pr.ParentProcessId; $a+=$p}}; $a -join ','"
        )
        try:
            code, out, _ = await run_process(
                ["powershell.exe", "-NoProfile", "-Command", script], timeout=5
            )
            if code != 0 or not out.strip():
                return []
            return [int(x) for x in out.strip().split(",") if x.strip().isdigit()]
        except Exception:
            return []

    script_unix = (
        f"pid={pid}; for i in $(seq 1 {max_depth}); do "
        "ppid=$(ps -o ppid= -p $pid 2>/dev/null | tr -d ' '); "
        "if [ -z \"$ppid\" ] || [ \"$ppid\" = \"0\" ] || [ \"$ppid\" = \"1\" ]; then break; fi; "
        "echo $ppid; pid=$ppid; done"
    )

    try:
        code, out, _ = await run_process(["sh", "-c", script_unix], timeout=5)
        if code != 0 or not out.strip():
            return []
        return [int(x) for x in out.strip().splitlines() if x.strip().isdigit()]
    except Exception:
        return []


def get_child_pids(pid: int) -> list[int]:
    """Return direct child PIDs of *pid* (synchronous)."""
    try:
        if platform.system() == "Windows":
            cmd = (
                f'(Get-CimInstance Win32_Process -Filter "ParentProcessId={pid}").ProcessId'
            )
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=5,
            )
            return [int(x) for x in result.stdout.strip().splitlines() if x.strip().isdigit()]
        else:
            result = subprocess.run(
                ["pgrep", "-P", str(pid)],
                capture_output=True, text=True, timeout=5,
            )
            return [int(x) for x in result.stdout.strip().splitlines() if x.strip().isdigit()]
    except Exception:
        return []

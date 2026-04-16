"""
Tmux socket isolation for Claude Code Python port.

Creates an isolated tmux socket (claude-<PID>) so Claude's tmux commands
never affect the user's own tmux sessions.

Key functions:
- ensure_socket_initialized()  – lazy init (safe to call multiple times)
- get_claude_tmux_env()        – TMUX env value for child processes
- check_tmux_available()       – one-shot availability check
"""
from __future__ import annotations

import asyncio
import os
import platform
import sys
from typing import Optional

TMUX_CMD = "tmux"
SOCKET_PREFIX = "claude"

# ── Module-level state ──────────────────────────────────────────────────────

_socket_name: Optional[str] = None
_socket_path: Optional[str] = None
_server_pid: Optional[int] = None
_init_lock: Optional[asyncio.Lock] = None
_initialized = False

_tmux_checked = False
_tmux_available = False
_tmux_tool_used = False


# ── Helpers ─────────────────────────────────────────────────────────────────

def _is_windows() -> bool:
    return sys.platform == "win32"


def _get_init_lock() -> asyncio.Lock:
    global _init_lock
    if _init_lock is None:
        _init_lock = asyncio.Lock()
    return _init_lock


async def _exec_tmux(args: list[str]) -> tuple[str, str, int]:
    """Run tmux (via WSL on Windows). Returns (stdout, stderr, returncode)."""
    if _is_windows():
        cmd = ["wsl", "-e", TMUX_CMD] + args
        env = {**os.environ, "WSL_UTF8": "1"}
    else:
        cmd = [TMUX_CMD] + args
        env = None

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout_b, stderr_b = await proc.communicate()
        return (
            stdout_b.decode(errors="replace"),
            stderr_b.decode(errors="replace"),
            proc.returncode or 0,
        )
    except FileNotFoundError:
        return ("", "command not found", 1)
    except Exception as exc:
        return ("", str(exc), 1)


# ── Public accessors ─────────────────────────────────────────────────────────

def get_claude_socket_name() -> str:
    global _socket_name
    if not _socket_name:
        _socket_name = f"{SOCKET_PREFIX}-{os.getpid()}"
    return _socket_name


def get_claude_socket_path() -> Optional[str]:
    return _socket_path


def set_claude_socket_info(path: str, pid: int) -> None:
    global _socket_path, _server_pid, _initialized
    _socket_path = path
    _server_pid = pid
    _initialized = True


def is_socket_initialized() -> bool:
    return _initialized


def get_claude_tmux_env() -> Optional[str]:
    """
    Return TMUX env value for child processes (socket_path,server_pid,0).
    Returns None if socket not yet initialized.
    """
    if not _socket_path or _server_pid is None:
        return None
    return f"{_socket_path},{_server_pid},0"


def is_tmux_available() -> bool:
    return _tmux_checked and _tmux_available


def mark_tmux_tool_used() -> None:
    global _tmux_tool_used
    _tmux_tool_used = True


def has_tmux_tool_been_used() -> bool:
    return _tmux_tool_used


# ── Availability check ───────────────────────────────────────────────────────

async def check_tmux_available() -> bool:
    global _tmux_checked, _tmux_available
    if not _tmux_checked:
        if _is_windows():
            _, _, code = await _exec_tmux(["-V"])
        else:
            try:
                proc = await asyncio.create_subprocess_exec(
                    "which", TMUX_CMD,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
                await proc.wait()
                code = proc.returncode or 0
            except Exception:
                code = 1
        _tmux_available = (code == 0)
        _tmux_checked = True
    return _tmux_available


# ── Initialization ───────────────────────────────────────────────────────────

async def _kill_tmux_server() -> None:
    socket = get_claude_socket_name()
    await _exec_tmux(["-L", socket, "kill-server"])


async def _do_initialize() -> None:
    socket = get_claude_socket_name()

    new_session_args = ["-L", socket, "new-session", "-d", "-s", "base",
                        "-e", "CLAUDE_CODE_SKIP_PROMPT_HISTORY=true"]
    if _is_windows():
        new_session_args += ["-e", "WSL_INTEROP=/run/WSL/1_interop"]

    stdout, stderr, code = await _exec_tmux(new_session_args)
    if code != 0:
        # Session may already exist
        _, _, check_code = await _exec_tmux(["-L", socket, "has-session", "-t", "base"])
        if check_code != 0:
            raise RuntimeError(f"Failed to create tmux session on {socket}: {stderr}")

    # Register cleanup
    try:
        import atexit
        atexit.register(lambda: asyncio.ensure_future(_kill_tmux_server()))
    except Exception:
        pass

    # Set global env in tmux server
    await _exec_tmux(["-L", socket, "set-environment", "-g",
                      "CLAUDE_CODE_SKIP_PROMPT_HISTORY", "true"])
    if _is_windows():
        await _exec_tmux(["-L", socket, "set-environment", "-g",
                          "WSL_INTEROP", "/run/WSL/1_interop"])

    # Discover socket path and server PID
    out, _, code = await _exec_tmux(["-L", socket, "display-message", "-p",
                                     "#{socket_path},#{pid}"])
    if code == 0:
        parts = out.strip().split(",")
        if len(parts) >= 2:
            try:
                pid = int(parts[1])
                set_claude_socket_info(parts[0], pid)
                return
            except ValueError:
                pass

    # Fallback: construct path manually
    uid = os.getuid() if hasattr(os, "getuid") else 0
    tmp = os.environ.get("TMPDIR", "/tmp")
    fallback_path = f"{tmp}/tmux-{uid}/{socket}"

    out, _, code = await _exec_tmux(["-L", socket, "display-message", "-p", "#{pid}"])
    if code == 0:
        try:
            pid = int(out.strip())
            set_claude_socket_info(fallback_path, pid)
            return
        except ValueError:
            pass

    raise RuntimeError(f"Failed to get socket info for {socket}")


async def ensure_socket_initialized() -> None:
    """Lazy init – safe to call multiple times; only initializes once."""
    if _initialized:
        return
    if not await check_tmux_available():
        return
    async with _get_init_lock():
        if _initialized:
            return
        try:
            await _do_initialize()
        except Exception as exc:
            # Graceful degradation – log and continue without isolation
            import logging
            logging.getLogger(__name__).warning(
                "tmux socket init failed, isolation disabled: %s", exc
            )


# ── Test helpers ─────────────────────────────────────────────────────────────

def reset_socket_state() -> None:
    global _socket_name, _socket_path, _server_pid, _init_lock
    global _initialized, _tmux_checked, _tmux_available, _tmux_tool_used
    _socket_name = _socket_path = _server_pid = _init_lock = None
    _initialized = _tmux_checked = _tmux_available = _tmux_tool_used = False

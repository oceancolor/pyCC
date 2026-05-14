"""Terminal launcher for deep links. Ported from utils/deepLink/terminalLauncher.ts"""

from __future__ import annotations

import asyncio
import os
import shlex
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from .terminal_preference import get_preferred_terminal


async def launch_in_terminal(
    claude_executable: str,
    cwd: str,
    prefill: Optional[str] = None,
    deep_link_origin: bool = False,
    repo: Optional[str] = None,
    last_fetch: Optional[datetime] = None,
) -> bool:
    """Open a new terminal window running Claude Code.

    Detects the user's preferred terminal emulator and launches Claude Code
    inside it. Used by the deep-link protocol handler when the OS invokes
    the binary directly (no TTY attached).

    Args:
        claude_executable: Absolute path to the Claude Code binary / interpreter.
        cwd: Working directory for the new session.
        prefill: Optional prompt text to pre-fill the input box.
        deep_link_origin: Whether to pass ``--deep-link-origin`` flag.
        repo: Optional repo slug (for banner display).
        last_fetch: Optional last-fetch timestamp (for banner display).

    Returns:
        True if the terminal was launched successfully, False otherwise.
    """
    terminal = await get_preferred_terminal()
    if not terminal:
        return False

    # Build the claude command arguments
    claude_args = [claude_executable]
    if deep_link_origin:
        claude_args.append("--deep-link-origin")
    if prefill:
        claude_args.extend(["--prefill", prefill])

    return await _launch_with_terminal(terminal, claude_args, cwd)


async def _launch_with_terminal(
    terminal: dict,
    claude_args: list,
    cwd: str,
) -> bool:
    """Launch the given command in the specified terminal emulator."""
    name: str = terminal.get("name", "")
    command: str = terminal.get("command", "")
    platform = sys.platform

    try:
        if platform == "darwin":
            return await _launch_macos(name, command, claude_args, cwd)
        if platform.startswith("linux"):
            return await _launch_linux(command, claude_args, cwd)
        if platform == "win32":
            return await _launch_windows(command, claude_args, cwd)
    except Exception:
        pass
    return False


async def _launch_macos(
    name: str, command: str, claude_args: list, cwd: str
) -> bool:
    """Launch in a macOS terminal application."""
    joined = shlex.join(claude_args)
    # Use 'open -a' for .app bundles; fall back to direct exec for CLI tools
    if name in ("iTerm2", "Ghostty", "Terminal"):
        script = (
            f'tell application "{name}" to do script '
            f'"cd {shlex.quote(cwd)} && {joined}"'
        )
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    else:
        proc = await asyncio.create_subprocess_exec(
            command,
            "--",
            "bash", "-c",
            f"cd {shlex.quote(cwd)} && {joined}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    await proc.communicate()
    return proc.returncode == 0


async def _launch_linux(command: str, claude_args: list, cwd: str) -> bool:
    """Launch in a Linux terminal emulator."""
    joined = shlex.join(claude_args)
    proc = await asyncio.create_subprocess_exec(
        command, "-e",
        "bash", "-c",
        f"cd {shlex.quote(cwd)} && {joined}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()
    return proc.returncode == 0


async def _launch_windows(command: str, claude_args: list, cwd: str) -> bool:
    """Launch in a Windows terminal emulator."""
    joined = " ".join(shlex.quote(a) for a in claude_args)
    proc = await asyncio.create_subprocess_exec(
        command,
        f"/c", f"cd /d {cwd} && {joined}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.communicate()
    return proc.returncode == 0

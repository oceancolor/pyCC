"""Terminal preference detection for deep link launching. Ported from utils/deepLink/terminalPreference.ts"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
from typing import Optional


async def get_preferred_terminal() -> Optional[dict]:
    """Detect the user's preferred terminal emulator.

    Returns a dict with ``name`` and ``command`` keys, or None if no supported
    terminal was found.

    Detection priority (platform-specific):
    - macOS: iTerm2 → Ghostty → Terminal.app → kitty → alacritty
    - Linux: TERMINAL env var → x-terminal-emulator → gnome-terminal → xterm
    - Windows: Windows Terminal (wt.exe) → PowerShell → cmd.exe
    """
    platform = sys.platform

    if platform == "darwin":
        return await _detect_macos_terminal()
    if platform.startswith("linux"):
        return _detect_linux_terminal()
    if platform == "win32":
        return _detect_windows_terminal()
    return None


async def _detect_macos_terminal() -> Optional[dict]:
    """Detect macOS terminal emulator by checking running apps."""
    # Check whether known terminals are running using osascript
    terminals = [
        {"name": "iTerm2", "command": "iTerm"},
        {"name": "Ghostty", "command": "ghostty"},
        {"name": "Terminal", "command": "Terminal"},
    ]
    for terminal in terminals:
        if await _is_macos_app_running(terminal["name"]):
            return terminal

    # Fallback: look for CLI terminal emulators
    for cli_terminal in ["kitty", "alacritty", "wezterm"]:
        if shutil.which(cli_terminal):
            return {"name": cli_terminal, "command": cli_terminal}

    # Last resort: Terminal.app
    return {"name": "Terminal", "command": "Terminal"}


async def _is_macos_app_running(app_name: str) -> bool:
    """Return True if the named macOS application is currently running."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e",
            f'tell application "System Events" to (name of processes) contains "{app_name}"',
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        return stdout.decode().strip() == "true"
    except Exception:
        return False


def _detect_linux_terminal() -> Optional[dict]:
    """Detect a suitable Linux terminal emulator."""
    # Honour explicit user preference
    env_terminal = os.environ.get("TERMINAL")
    if env_terminal and shutil.which(env_terminal):
        return {"name": env_terminal, "command": env_terminal}

    # Try well-known terminals in preference order
    for name in [
        "x-terminal-emulator",
        "gnome-terminal",
        "konsole",
        "xfce4-terminal",
        "xterm",
        "kitty",
        "alacritty",
    ]:
        if shutil.which(name):
            return {"name": name, "command": name}

    return None


def _detect_windows_terminal() -> Optional[dict]:
    """Detect a suitable Windows terminal emulator."""
    # Windows Terminal
    wt = shutil.which("wt.exe") or shutil.which("wt")
    if wt:
        return {"name": "Windows Terminal", "command": wt}

    # PowerShell
    ps = shutil.which("pwsh.exe") or shutil.which("pwsh") or shutil.which("powershell.exe")
    if ps:
        return {"name": "PowerShell", "command": ps}

    # cmd.exe
    cmd = shutil.which("cmd.exe") or shutil.which("cmd")
    if cmd:
        return {"name": "cmd", "command": cmd}

    return None

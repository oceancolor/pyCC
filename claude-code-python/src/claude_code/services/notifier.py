# 原始 TS: services/notifier.ts
"""System notification service.

Routes notifications to the appropriate channel (terminal bell, iTerm2,
macOS native, tmux, etc.) and executes registered notification hooks.
"""
from __future__ import annotations

import asyncio
import logging
import platform
import subprocess
from dataclasses import dataclass
from typing import Literal

logger = logging.getLogger(__name__)

NotificationChannel = Literal["auto", "terminal_bell", "iterm2", "native", "tmux", "none"]

DEFAULT_TITLE = "Claude Code"


@dataclass
class NotificationOptions:
    message: str
    title: str = DEFAULT_TITLE
    notification_type: str = "general"


async def send_notification(
    notif: NotificationOptions,
    preferred_channel: NotificationChannel = "auto",
) -> str:
    """Send a desktop/terminal notification and return the channel used."""
    method = await _send_to_channel(preferred_channel, notif)
    logger.debug("Notification sent via '%s': %s", method, notif.message)
    return method


async def _send_to_channel(channel: NotificationChannel, opts: NotificationOptions) -> str:
    """Dispatch to the requested channel, falling back gracefully."""
    if channel == "none":
        return "none"

    if channel == "auto":
        return await _send_auto(opts)

    dispatchers: dict[str, Any] = {
        "terminal_bell": _send_terminal_bell,
        "iterm2": _send_iterm2,
        "native": _send_native,
        "tmux": _send_tmux,
    }
    fn = dispatchers.get(channel)
    if fn:
        try:
            return await fn(opts)
        except Exception:  # noqa: BLE001
            pass

    return await _send_terminal_bell(opts)


async def _send_auto(opts: NotificationOptions) -> str:
    """Try channels in preference order."""
    sys = platform.system()

    # macOS: try native notification
    if sys == "Darwin":
        try:
            return await _send_native(opts)
        except Exception:  # noqa: BLE001
            pass

    # Linux: try libnotify
    if sys == "Linux":
        try:
            return await _send_linux_notify(opts)
        except Exception:  # noqa: BLE001
            pass

    # Fallback: terminal bell
    return await _send_terminal_bell(opts)


async def _send_terminal_bell(opts: NotificationOptions) -> str:  # noqa: ARG001
    """Print BEL character to trigger a terminal bell."""
    print("\a", end="", flush=True)
    return "terminal_bell"


async def _send_iterm2(opts: NotificationOptions) -> str:
    """Send an iTerm2 proprietary notification via escape sequence."""
    # iTerm2 notification: ESC ] 9 ; <message> BEL
    seq = f"\x1b]9;{opts.message}\a"
    print(seq, end="", flush=True)
    return "iterm2"


async def _send_native(opts: NotificationOptions) -> str:
    """macOS native notification via osascript."""
    escaped_msg = opts.message.replace('"', '\\"')
    escaped_title = opts.title.replace('"', '\\"')
    script = f'display notification "{escaped_msg}" with title "{escaped_title}"'
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return "native"


async def _send_linux_notify(opts: NotificationOptions) -> str:
    """Linux desktop notification via notify-send."""
    proc = await asyncio.create_subprocess_exec(
        "notify-send", opts.title, opts.message,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return "linux_notify"


async def _send_tmux(opts: NotificationOptions) -> str:
    """Tmux display-message notification."""
    msg = opts.message[:200]  # tmux message length limit
    proc = await asyncio.create_subprocess_exec(
        "tmux", "display-message", f"[Claude] {msg}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return "tmux"


# Type stub to satisfy static analysis above
from typing import Any  # noqa: E402

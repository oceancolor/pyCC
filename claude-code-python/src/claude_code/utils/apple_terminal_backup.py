"""Apple Terminal preference backup/restore. Ported from utils/appleTerminalBackup.ts"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Optional


def get_terminal_plist_path() -> str:
    """Return the path to the Apple Terminal preferences plist."""
    return str(Path.home() / "Library" / "Preferences" / "com.apple.Terminal.plist")


def mark_terminal_setup_in_progress(backup_path: str) -> None:
    """Record in global config that Terminal setup is underway."""
    if sys.platform != "darwin":
        return
    try:
        from claude_code.utils.config import get_global_config, save_global_config

        save_global_config(
            lambda c: {
                **c,
                "appleTerminalSetupInProgress": True,
                "appleTerminalBackupPath": backup_path,
            }
        )
    except Exception:
        pass


def mark_terminal_setup_complete() -> None:
    """Clear the Terminal setup-in-progress flag from global config."""
    if sys.platform != "darwin":
        return
    try:
        from claude_code.utils.config import save_global_config

        save_global_config(lambda c: {**c, "appleTerminalSetupInProgress": False})
    except Exception:
        pass


def get_terminal_recovery_info() -> dict:
    """Return the in-progress flag and backup path from global config."""
    try:
        from claude_code.utils.config import get_global_config

        config = get_global_config()
        return {
            "in_progress": getattr(config, "apple_terminal_setup_in_progress", False) or False,
            "backup_path": getattr(config, "apple_terminal_backup_path", None),
        }
    except Exception:
        return {"in_progress": False, "backup_path": None}


async def backup_terminal_preferences() -> Optional[str]:
    """Export Apple Terminal preferences to a backup file.

    Returns the backup file path on success, or None on failure.
    Only runs on macOS.
    """
    if sys.platform != "darwin":
        return None

    plist_path = get_terminal_plist_path()
    backup_path = plist_path + ".bak"

    try:
        proc = await asyncio.create_subprocess_exec(
            "defaults", "export", "com.apple.Terminal", plist_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        if proc.returncode != 0:
            return None

        if not os.path.exists(plist_path):
            return None

        proc2 = await asyncio.create_subprocess_exec(
            "defaults", "export", "com.apple.Terminal", backup_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc2.communicate()
        if proc2.returncode != 0:
            return None

        return backup_path
    except Exception:
        return None


async def restore_terminal_preferences(backup_path: str) -> bool:
    """Restore Apple Terminal preferences from a backup file.

    Returns True on success.
    """
    if sys.platform != "darwin":
        return False

    if not os.path.exists(backup_path):
        return False

    try:
        proc = await asyncio.create_subprocess_exec(
            "defaults", "import", "com.apple.Terminal", backup_path,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        return proc.returncode == 0
    except Exception:
        return False

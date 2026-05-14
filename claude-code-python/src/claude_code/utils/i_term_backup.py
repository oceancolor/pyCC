"""iTerm2 preference backup/restore. Ported from utils/iTermBackup.ts"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Literal, Optional


def _get_iterm2_plist_path() -> str:
    """Return the path to the iTerm2 preferences plist."""
    return str(
        Path.home() / "Library" / "Preferences" / "com.googlecode.iterm2.plist"
    )


def mark_iterm2_setup_complete() -> None:
    """Clear the iTerm2 setup-in-progress flag from global config."""
    if sys.platform != "darwin":
        return
    try:
        from claude_code.utils.config import save_global_config

        save_global_config(lambda c: {**c, "iterm2SetupInProgress": False})
    except Exception:
        pass


def get_iterm2_recovery_info() -> dict:
    """Return iTerm2 setup progress and backup path from global config."""
    try:
        from claude_code.utils.config import get_global_config

        config = get_global_config()
        return {
            "in_progress": getattr(config, "iterm2_setup_in_progress", False) or False,
            "backup_path": getattr(config, "iterm2_backup_path", None),
        }
    except Exception:
        return {"in_progress": False, "backup_path": None}


async def backup_iterm2_preferences() -> Optional[str]:
    """Copy the iTerm2 plist to a backup file.

    Returns the backup file path on success, or None on failure.
    Only runs on macOS.
    """
    if sys.platform != "darwin":
        return None

    plist_path = _get_iterm2_plist_path()
    backup_path = plist_path + ".bak"

    if not os.path.exists(plist_path):
        return None

    try:
        loop = asyncio.get_event_loop()
        import shutil

        await loop.run_in_executor(None, lambda: shutil.copy2(plist_path, backup_path))
        return backup_path
    except Exception:
        return None


async def check_and_restore_iterm2_backup() -> dict:
    """Check for a pending iTerm2 backup and restore it if present.

    Returns a dict with key ``status`` in ('restored', 'no_backup', 'failed').
    The 'failed' variant also includes a ``backup_path`` key.
    """
    info = get_iterm2_recovery_info()
    if not info["in_progress"]:
        return {"status": "no_backup"}

    backup_path = info["backup_path"]
    if not backup_path:
        mark_iterm2_setup_complete()
        return {"status": "no_backup"}

    if not os.path.exists(backup_path):
        mark_iterm2_setup_complete()
        return {"status": "no_backup"}

    plist_path = _get_iterm2_plist_path()

    try:
        loop = asyncio.get_event_loop()
        import shutil

        await loop.run_in_executor(None, lambda: shutil.copy2(backup_path, plist_path))
        mark_iterm2_setup_complete()
        return {"status": "restored"}
    except Exception:
        return {"status": "failed", "backup_path": backup_path}

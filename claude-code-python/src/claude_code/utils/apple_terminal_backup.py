"""Apple Terminal preferences backup/restore. Ported from utils/appleTerminalBackup.ts"""
from __future__ import annotations
import asyncio
import os
from pathlib import Path
from typing import Optional

from claude_code.utils.exec_file_no_throw import exec_file_no_throw


def get_terminal_plist_path() -> str:
    return str(Path.home() / "Library" / "Preferences" / "com.apple.Terminal.plist")


async def backup_terminal_preferences() -> Optional[str]:
    plist = get_terminal_plist_path()
    backup = plist + ".bak"
    result = await exec_file_no_throw("defaults", ["export", "com.apple.Terminal", backup])
    if result.get("code") != 0:
        return None
    return backup


async def restore_terminal_preferences(backup_path: str) -> bool:
    result = await exec_file_no_throw("defaults", ["import", "com.apple.Terminal", backup_path])
    return result.get("code") == 0

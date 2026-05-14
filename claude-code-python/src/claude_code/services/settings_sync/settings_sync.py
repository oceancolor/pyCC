"""Settings sync service. Ported from services/settingsSync/settingsSync.ts"""
from __future__ import annotations
import time
from typing import Any, Dict

_last_sync: float = 0.0
_is_synced: bool = False


async def sync_settings() -> None:
    """Sync local settings to/from the remote settings service."""
    global _last_sync, _is_synced
    try:
        from claude_code.services.remote_managed_settings.remote_managed_settings import (
            load_remote_managed_settings,
        )
        await load_remote_managed_settings()
        _last_sync = time.time()
        _is_synced = True
    except Exception:
        _is_synced = False


async def get_remote_settings() -> Dict[str, Any]:
    """Return the latest remote settings, fetching if not yet loaded."""
    try:
        from claude_code.services.remote_managed_settings.remote_managed_settings import (
            get_remote_managed_settings,
        )
        return await get_remote_managed_settings()
    except Exception:
        return {}


def get_sync_status() -> Dict[str, Any]:
    """Return the current settings sync status."""
    return {
        "synced": _is_synced,
        "last_sync": _last_sync,
    }

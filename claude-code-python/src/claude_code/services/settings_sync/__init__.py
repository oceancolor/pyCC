"""Settings sync service.

Synchronises the local Claude Code settings with a remote settings store,
allowing settings to roam across machines.  Also exposes helpers for
reading the current remote settings and querying the sync status.

Ported from: src/services/settingsSync/ (TypeScript)

Usage::

    from claude_code.services.settings_sync import (
        sync_settings,
        get_remote_settings,
        get_sync_status,
        SyncStatus,
    )
"""
from __future__ import annotations

from claude_code.services.settings_sync.settings_sync import (
    sync_settings,
    get_remote_settings,
    get_sync_status,
)
from claude_code.services.settings_sync.types import SyncStatus

__all__ = [
    "sync_settings",
    "get_remote_settings",
    "get_sync_status",
    "SyncStatus",
]

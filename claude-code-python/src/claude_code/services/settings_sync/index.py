"""Settings sync service index.

Re-exports the public API of the settings sync service for consumers
that import from the ``index`` module rather than the package root.

Ported from: src/services/settingsSync/index.ts (TypeScript)

Usage::

    from claude_code.services.settings_sync.index import (
        sync_settings,
        get_remote_settings,
        get_sync_status,
    )
"""
from __future__ import annotations

from claude_code.services.settings_sync.settings_sync import (
    sync_settings,
    get_remote_settings,
    get_sync_status,
)

__all__ = [
    "sync_settings",
    "get_remote_settings",
    "get_sync_status",
]

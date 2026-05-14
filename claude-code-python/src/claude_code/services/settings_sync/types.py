"""Settings sync types. Ported from services/settingsSync/types.ts"""
from __future__ import annotations
from typing import Optional
try:
    from typing import TypedDict
except ImportError:
    from typing_extensions import TypedDict


class SyncStatus(TypedDict):
    """Current status of the settings sync service."""
    synced: bool
    last_sync: float


class SettingsSyncRecord(TypedDict, total=False):
    """A settings record produced by the sync service."""
    key: str
    value: object
    synced_at: Optional[float]
    version: int

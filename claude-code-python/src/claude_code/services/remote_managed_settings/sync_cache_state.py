"""Sync cache state. Stub."""
from __future__ import annotations
_state = {"last_sync": 0, "is_syncing": False}
def get_sync_state() -> dict: return dict(_state)

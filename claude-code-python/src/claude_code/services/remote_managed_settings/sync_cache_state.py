"""Sync cache state. Ported from services/remoteManagedSettings/syncCacheState.ts"""
from __future__ import annotations
import time

_state: dict = {"last_sync": 0.0, "is_syncing": False}


def get_sync_state() -> dict:
    """Return a copy of the current sync state."""
    return dict(_state)


def set_syncing(is_syncing: bool) -> None:
    """Update the syncing flag."""
    _state["is_syncing"] = is_syncing


def set_last_sync(timestamp: float = 0.0) -> None:
    """Record the last successful sync timestamp (epoch seconds)."""
    _state["last_sync"] = timestamp if timestamp else time.time()


def is_syncing() -> bool:
    """Return whether a sync is currently in progress."""
    return bool(_state["is_syncing"])


def get_last_sync() -> float:
    """Return the epoch timestamp of the last successful sync."""
    return float(_state["last_sync"])

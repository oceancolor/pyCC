"""Remote settings sync cache. Ported from services/remoteManagedSettings/syncCache.ts"""
from __future__ import annotations
from typing import Any

_cache: dict = {}


def get_cache() -> dict:
    """Return a shallow copy of the settings cache."""
    return dict(_cache)


def set_cache(key: str, value: Any) -> None:
    """Store a value in the settings cache."""
    _cache[key] = value


def clear_cache() -> None:
    """Clear all cached settings."""
    _cache.clear()


def get_cached_value(key: str, default: Any = None) -> Any:
    """Get a value from the settings cache with an optional default."""
    return _cache.get(key, default)


def update_cache(updates: dict) -> None:
    """Merge updates into the settings cache."""
    _cache.update(updates)

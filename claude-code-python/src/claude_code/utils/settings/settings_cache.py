"""
Settings cache - caches loaded settings to avoid repeated disk reads.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

_settings_cache: Optional[Dict[str, Any]] = None


def get_cached_settings() -> Optional[Dict[str, Any]]:
    """Get cached settings if available."""
    return _settings_cache


def set_cached_settings(settings: Dict[str, Any]) -> None:
    """Store settings in cache."""
    global _settings_cache
    _settings_cache = settings


def reset_settings_cache() -> None:
    """Reset the settings cache."""
    global _settings_cache
    _settings_cache = None


def get_or_load_settings(loader: Any) -> Dict[str, Any]:
    """Get cached settings or load fresh from the given loader function."""
    global _settings_cache
    if _settings_cache is None:
        _settings_cache = loader()
    return _settings_cache

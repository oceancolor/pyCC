"""
Cache utils - utilities for plugin caching operations.
"""

from __future__ import annotations

import hashlib
import os
from typing import Optional


def get_cache_key(url: str, version: Optional[str] = None) -> str:
    """Generate a cache key for a plugin URL and version."""
    key_str = f"{url}@{version or 'latest'}"
    return hashlib.sha256(key_str.encode()).hexdigest()[:16]


def is_cached(cache_dir: str, key: str) -> bool:
    """Check if a plugin is cached."""
    return os.path.exists(os.path.join(cache_dir, key))


def get_cached_path(cache_dir: str, key: str) -> Optional[str]:
    """Get the path to a cached plugin, or None if not cached."""
    path = os.path.join(cache_dir, key)
    return path if os.path.exists(path) else None


def invalidate_cache(cache_dir: str, key: str) -> None:
    """Invalidate a cached plugin."""
    import shutil
    path = os.path.join(cache_dir, key)
    if os.path.exists(path):
        if os.path.isdir(path):
            shutil.rmtree(path)
        else:
            os.remove(path)

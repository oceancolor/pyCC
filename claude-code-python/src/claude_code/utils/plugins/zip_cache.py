"""
Zip cache - caches downloaded plugin zip files.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from typing import Optional


def get_zip_cache_dir() -> str:
    """Get the zip cache directory."""
    return os.path.expanduser("~/.claude/plugins/cache/zips")


def get_cached_zip_path(url: str) -> Optional[str]:
    """Get the cached zip path for a URL, if it exists."""
    cache_key = _url_to_cache_key(url)
    path = os.path.join(get_zip_cache_dir(), cache_key + ".zip")
    return path if os.path.exists(path) else None


def cache_zip(url: str, zip_data: bytes) -> str:
    """Cache zip data for a URL. Returns the cached file path."""
    cache_dir = get_zip_cache_dir()
    os.makedirs(cache_dir, exist_ok=True)
    cache_key = _url_to_cache_key(url)
    path = os.path.join(cache_dir, cache_key + ".zip")
    with open(path, "wb") as f:
        f.write(zip_data)
    return path


def invalidate_zip_cache(url: str) -> None:
    """Remove cached zip for a URL."""
    cached = get_cached_zip_path(url)
    if cached and os.path.exists(cached):
        os.remove(cached)


def clear_zip_cache() -> None:
    """Clear the entire zip cache."""
    cache_dir = get_zip_cache_dir()
    if os.path.isdir(cache_dir):
        shutil.rmtree(cache_dir)


def _url_to_cache_key(url: str) -> str:
    """Convert a URL to a filesystem-safe cache key."""
    return hashlib.sha256(url.encode()).hexdigest()[:32]

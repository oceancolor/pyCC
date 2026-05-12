"""
Zip cache adapters - different storage backends for the zip cache.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol


class ZipCacheAdapter(Protocol):
    """Protocol for zip cache storage adapters."""

    async def get(self, key: str) -> Optional[bytes]:
        """Get cached zip data by key. Returns None if not cached."""
        ...

    async def set(self, key: str, data: bytes) -> None:
        """Store zip data with the given key."""
        ...

    async def delete(self, key: str) -> None:
        """Delete cached zip data by key."""
        ...

    async def clear(self) -> None:
        """Clear all cached zip data."""
        ...


class FileSystemZipCacheAdapter:
    """File-system backed zip cache adapter."""

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        import os
        self._cache_dir = cache_dir or os.path.expanduser("~/.claude/plugins/cache/zips")

    async def get(self, key: str) -> Optional[bytes]:
        import os
        path = os.path.join(self._cache_dir, key)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception:
            return None

    async def set(self, key: str, data: bytes) -> None:
        import os
        os.makedirs(self._cache_dir, exist_ok=True)
        path = os.path.join(self._cache_dir, key)
        with open(path, "wb") as f:
            f.write(data)

    async def delete(self, key: str) -> None:
        import os
        path = os.path.join(self._cache_dir, key)
        if os.path.exists(path):
            os.remove(path)

    async def clear(self) -> None:
        import shutil
        if __import__("os").path.isdir(self._cache_dir):
            shutil.rmtree(self._cache_dir)


class MemoryZipCacheAdapter:
    """In-memory zip cache adapter (for testing)."""

    def __init__(self) -> None:
        self._cache: dict = {}

    async def get(self, key: str) -> Optional[bytes]:
        return self._cache.get(key)

    async def set(self, key: str, data: bytes) -> None:
        self._cache[key] = data

    async def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    async def clear(self) -> None:
        self._cache.clear()


def create_default_zip_cache_adapter() -> FileSystemZipCacheAdapter:
    """Create the default file-system backed zip cache adapter."""
    return FileSystemZipCacheAdapter()

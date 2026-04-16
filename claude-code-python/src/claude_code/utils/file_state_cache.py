"""
Python port of: src/utils/fileStateCache.ts
LRU-based file state cache with path normalisation.

Requires: pip install lru-dict  (or use the pure-Python fallback below)
We ship a pure-Python OrderedDict-based LRU to avoid the extra dependency.
"""

from __future__ import annotations

import os
import sys
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Generator, Iterator, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

READ_FILE_STATE_CACHE_SIZE: int = 100
_DEFAULT_MAX_CACHE_SIZE_BYTES: int = 25 * 1024 * 1024  # 25 MB


# ---------------------------------------------------------------------------
# FileState dataclass (replaces the TS type)
# ---------------------------------------------------------------------------

@dataclass
class FileState:
    """Represents a cached view of a file."""

    content: str
    timestamp: float  # Unix epoch seconds (float for sub-second precision)
    offset: Optional[int] = None
    limit: Optional[int] = None
    #: True when this entry was populated by auto-injection (e.g. CLAUDE.md)
    #: and the injected content did not match disk.  The model has only seen
    #: a partial view; Edit/Write must require an explicit Read first.
    #: `content` holds the RAW disk bytes (for diffing), not what the model saw.
    is_partial_view: Optional[bool] = None


# ---------------------------------------------------------------------------
# Pure-Python LRU cache with size eviction
# ---------------------------------------------------------------------------

class _SizedLRU:
    """
    A minimal LRU cache that supports:
    - max entries (count-based eviction)
    - max size in bytes (size-based eviction)

    Keys are always strings.  Values are FileState objects.
    """

    def __init__(self, max_entries: int, max_size_bytes: int) -> None:
        self._max_entries = max_entries
        self._max_size_bytes = max_size_bytes
        self._store: OrderedDict[str, FileState] = OrderedDict()
        self._sizes: dict[str, int] = {}
        self._total_size: int = 0

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _calc_size(self, value: FileState) -> int:
        """Approximate byte size of a cached entry (content only)."""
        return max(1, len(value.content.encode("utf-8")))

    def _evict_if_needed(self) -> None:
        """Evict oldest entries until within limits."""
        while self._store and (
            len(self._store) > self._max_entries
            or self._total_size > self._max_size_bytes
        ):
            oldest_key, _ = next(iter(self._store.items()))
            self._remove(oldest_key)

    def _remove(self, key: str) -> None:
        if key in self._store:
            self._total_size -= self._sizes.pop(key, 0)
            del self._store[key]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[FileState]:
        if key not in self._store:
            return None
        # Move to end (most-recently-used)
        self._store.move_to_end(key)
        return self._store[key]

    def set(self, key: str, value: FileState) -> None:
        if key in self._store:
            self._remove(key)
        size = self._calc_size(value)
        self._store[key] = value
        self._sizes[key] = size
        self._total_size += size
        self._evict_if_needed()

    def has(self, key: str) -> bool:
        return key in self._store

    def delete(self, key: str) -> bool:
        if key in self._store:
            self._remove(key)
            return True
        return False

    def clear(self) -> None:
        self._store.clear()
        self._sizes.clear()
        self._total_size = 0

    @property
    def size(self) -> int:
        return len(self._store)

    @property
    def max(self) -> int:
        return self._max_entries

    @property
    def max_size(self) -> int:
        return self._max_size_bytes

    @property
    def calculated_size(self) -> int:
        return self._total_size

    def keys(self) -> Iterator[str]:
        return iter(list(self._store.keys()))

    def entries(self) -> Iterator[Tuple[str, FileState]]:
        return iter(list(self._store.items()))

    def dump(self) -> List[Tuple[str, FileState]]:
        """Return a snapshot of all entries ordered oldest-first."""
        return list(self._store.items())

    def load(self, entries: List[Tuple[str, FileState]]) -> None:
        """Restore entries from a dump() snapshot."""
        for key, value in entries:
            self.set(key, value)


# ---------------------------------------------------------------------------
# FileStateCache  (public API mirrors the TS class)
# ---------------------------------------------------------------------------

class FileStateCache:
    """
    A file state cache that normalises all path keys before access.

    This ensures consistent cache hits regardless of whether callers pass
    relative vs absolute paths with redundant segments (e.g. /foo/../bar).
    """

    def __init__(self, max_entries: int, max_size_bytes: int) -> None:
        self._cache = _SizedLRU(max_entries, max_size_bytes)

    # ------------------------------------------------------------------
    # Key normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _norm(key: str) -> str:
        return os.path.normpath(key)

    # ------------------------------------------------------------------
    # Dict-like interface
    # ------------------------------------------------------------------

    def get(self, key: str) -> Optional[FileState]:
        return self._cache.get(self._norm(key))

    def set(self, key: str, value: FileState) -> "FileStateCache":
        self._cache.set(self._norm(key), value)
        return self

    def has(self, key: str) -> bool:
        return self._cache.has(self._norm(key))

    def delete(self, key: str) -> bool:
        return self._cache.delete(self._norm(key))

    def clear(self) -> None:
        self._cache.clear()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def size(self) -> int:
        return self._cache.size

    @property
    def max(self) -> int:
        return self._cache.max

    @property
    def max_size(self) -> int:
        return self._cache.max_size

    @property
    def calculated_size(self) -> int:
        return self._cache.calculated_size

    # ------------------------------------------------------------------
    # Iteration / serialisation
    # ------------------------------------------------------------------

    def keys(self) -> Iterator[str]:
        return self._cache.keys()

    def entries(self) -> Iterator[Tuple[str, FileState]]:
        return self._cache.entries()

    def dump(self) -> List[Tuple[str, FileState]]:
        return self._cache.dump()

    def load(self, entries: List[Tuple[str, FileState]]) -> None:
        self._cache.load(entries)


# ---------------------------------------------------------------------------
# Factory & helpers
# ---------------------------------------------------------------------------

def create_file_state_cache_with_size_limit(
    max_entries: int,
    max_size_bytes: int = _DEFAULT_MAX_CACHE_SIZE_BYTES,
) -> FileStateCache:
    """Factory: create a size-limited FileStateCache."""
    return FileStateCache(max_entries, max_size_bytes)


def cache_to_object(cache: FileStateCache) -> dict[str, FileState]:
    """Convert cache to a plain dict (used by compact logic)."""
    return dict(cache.entries())


def cache_keys(cache: FileStateCache) -> List[str]:
    """Return all cache keys as a list."""
    return list(cache.keys())


def clone_file_state_cache(cache: FileStateCache) -> FileStateCache:
    """Deep-clone a FileStateCache, preserving size configuration."""
    cloned = create_file_state_cache_with_size_limit(cache.max, cache.max_size)
    cloned.load(cache.dump())
    return cloned


def merge_file_state_caches(
    first: FileStateCache,
    second: FileStateCache,
) -> FileStateCache:
    """
    Merge two caches.  For conflicting keys, keep the entry with the
    more recent timestamp.
    """
    merged = clone_file_state_cache(first)
    for file_path, file_state in second.entries():
        existing = merged.get(file_path)
        if not existing or file_state.timestamp > existing.timestamp:
            merged.set(file_path, file_state)
    return merged

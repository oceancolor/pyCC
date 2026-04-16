# 原始 TS: utils/memoize.ts
"""Memoization utilities with TTL and LRU support."""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from typing import Any, Callable, Generic, Optional, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# ---------------------------------------------------------------------------
# Simple LRU cache with explicit size / clear / delete / get / has API
# ---------------------------------------------------------------------------

class LRUCache(Generic[TypeVar("K"), TypeVar("V")]):  # type: ignore[misc]
    """A small LRU cache backed by an OrderedDict."""

    def __init__(self, max_size: int = 128) -> None:
        self._max = max_size
        self._data: OrderedDict = OrderedDict()

    # --- dict-like interface ---

    def get(self, key: Any, default: Any = None) -> Any:
        if key not in self._data:
            return default
        self._data.move_to_end(key)
        return self._data[key]

    def set(self, key: Any, value: Any) -> None:
        if key in self._data:
            self._data.move_to_end(key)
        self._data[key] = value
        if len(self._data) > self._max:
            self._data.popitem(last=False)

    def has(self, key: Any) -> bool:
        return key in self._data

    def delete(self, key: Any) -> bool:
        if key in self._data:
            del self._data[key]
            return True
        return False

    def clear(self) -> None:
        self._data.clear()

    def size(self) -> int:
        return len(self._data)


# ---------------------------------------------------------------------------
# memoize_with_ttl
# ---------------------------------------------------------------------------

class _CacheEntry:
    __slots__ = ("value", "timestamp", "refreshing")

    def __init__(self, value: Any, timestamp: float) -> None:
        self.value = value
        self.timestamp = timestamp
        self.refreshing = False


def memoize_with_ttl(
    fn: Callable[..., Any],
    cache_lifetime_ms: float = 5 * 60 * 1000,
) -> Callable[..., Any]:
    """Create a memoized wrapper that returns stale values while refreshing.

    Write-through cache pattern:
    - Cache fresh → return immediately.
    - Cache stale → return stale value, kick off background refresh.
    - Cache missing → block and compute.

    Args:
        fn: The (synchronous or async) function to memoize.
        cache_lifetime_ms: Cache TTL in milliseconds (default 5 minutes).
    """
    cache: dict[str, _CacheEntry] = {}

    def _make_key(args: tuple, kwargs: dict) -> str:
        try:
            return json.dumps((args, sorted(kwargs.items())), default=str)
        except Exception:
            return repr((args, kwargs))

    def _is_stale(entry: _CacheEntry) -> bool:
        age_ms = (time.monotonic() - entry.timestamp) * 1000
        return age_ms > cache_lifetime_ms

    if asyncio.iscoroutinefunction(fn):
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _make_key(args, kwargs)
            entry = cache.get(key)
            now = time.monotonic()

            if entry is None:
                value = await fn(*args, **kwargs)
                cache[key] = _CacheEntry(value, now)
                return value

            if _is_stale(entry) and not entry.refreshing:
                entry.refreshing = True

                async def _refresh() -> None:
                    try:
                        value = await fn(*args, **kwargs)
                        cache[key] = _CacheEntry(value, time.monotonic())
                    except Exception:
                        pass
                    finally:
                        if key in cache:
                            cache[key].refreshing = False

                asyncio.ensure_future(_refresh())

            return entry.value

        async_wrapper.cache = type(  # type: ignore[attr-defined]
            "_Cache", (), {"clear": lambda self: cache.clear()}
        )()
        return async_wrapper

    else:
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _make_key(args, kwargs)
            entry = cache.get(key)
            now = time.monotonic()

            if entry is None:
                value = fn(*args, **kwargs)
                cache[key] = _CacheEntry(value, now)
                return value

            if _is_stale(entry) and not entry.refreshing:
                # Can't do async background refresh in sync context; just
                # refresh synchronously (simpler than spawning a thread).
                entry.refreshing = True
                try:
                    value = fn(*args, **kwargs)
                    cache[key] = _CacheEntry(value, time.monotonic())
                except Exception:
                    pass
                finally:
                    if key in cache:
                        cache[key].refreshing = False

            return entry.value

        sync_wrapper.cache = type(  # type: ignore[attr-defined]
            "_Cache", (), {"clear": lambda self: cache.clear()}
        )()
        return sync_wrapper


# ---------------------------------------------------------------------------
# memoize_with_lru — keyed by JSON-serialised args, bounded cache
# ---------------------------------------------------------------------------

def memoize_with_lru(
    fn: Callable[..., Any],
    max_size: int = 128,
) -> Callable[..., Any]:
    """Memoize *fn* using an LRU cache keyed by JSON-serialised arguments."""
    _cache: LRUCache = LRUCache(max_size)

    def _key(args: tuple, kwargs: dict) -> str:
        try:
            return json.dumps((args, sorted(kwargs.items())), default=str)
        except Exception:
            return repr((args, kwargs))

    def wrapper(*args: Any, **kwargs: Any) -> Any:
        k = _key(args, kwargs)
        if _cache.has(k):
            return _cache.get(k)
        result = fn(*args, **kwargs)
        _cache.set(k, result)
        return result

    wrapper.cache = _cache  # type: ignore[attr-defined]
    return wrapper

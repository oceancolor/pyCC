"""Lazy schema factory. Ported from lazySchema.ts"""
from __future__ import annotations
from functools import lru_cache
from typing import Callable, TypeVar, Any

T = TypeVar("T")

def lazy_schema(factory: Callable[[], T]) -> Callable[[], T]:
    """Return a memoized factory that builds the schema on first call."""
    cache: list = []
    def get() -> T:
        if not cache:
            cache.append(factory())
        return cache[0]
    return get

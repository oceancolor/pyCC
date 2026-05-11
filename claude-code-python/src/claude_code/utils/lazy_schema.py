"""Lazy schema factory. Ported from utils/lazySchema.ts"""
from __future__ import annotations
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


def lazy_schema(factory: Callable[[], T]) -> Callable[[], T]:
    """Return a memoised factory that constructs the value on first call.

    Used to defer Zod / Pydantic schema construction from module import
    time to first access — avoids circular-import issues that arise when
    two schema modules reference each other at the top level.

    Ported from utils/lazySchema.ts: lazySchema.

    Example::

        input_schema = lazy_schema(lambda: SomeModel.schema())

        # Later:
        schema = input_schema()   # constructed once, then cached
    """
    _cache: list = []

    def _get() -> T:
        if not _cache:
            _cache.append(factory())
        return _cache[0]

    return _get

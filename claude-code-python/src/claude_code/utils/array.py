"""
Array utility functions
原始 TS: src/utils/array.ts
"""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, TypeVar

T = TypeVar("T")
U = TypeVar("U")


def unique(items: Iterable[T]) -> list[T]:
    """Remove duplicates while preserving order. lodash uniq → set + list"""
    seen: set = set()
    result: list[T] = []
    for item in items:
        if id(item) not in seen and item not in seen:
            seen.add(item)
            result.append(item)
    return result


def count(items: Iterable[T], predicate: Callable[[T], bool]) -> int:
    """Count items matching predicate. 原始 TS: count"""
    return sum(1 for item in items if predicate(item))


def flat_map(items: Iterable[T], fn: Callable[[T], Iterable[U]]) -> list[U]:
    """flatMap. 原始 TS: flatMap"""
    result: list[U] = []
    for item in items:
        result.extend(fn(item))
    return result


def group_by(items: Iterable[T], key_fn: Callable[[T], Any]) -> dict[Any, list[T]]:
    """Group items by key function. lodash groupBy"""
    result: dict[Any, list[T]] = {}
    for item in items:
        k = key_fn(item)
        if k not in result:
            result[k] = []
        result[k].append(item)
    return result


def last(items: list[T]) -> Optional[T]:
    """Get last item. lodash last"""
    return items[-1] if items else None


def chunk(items: list[T], size: int) -> list[list[T]]:
    """Split list into chunks. lodash chunk"""
    return [items[i: i + size] for i in range(0, len(items), size)]

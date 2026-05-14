"""Set utility functions. Ported from utils/set.ts.

Provides functional-style set operations as standalone functions.  The module
name ``set.py`` mirrors the TypeScript ``set.ts`` source; it shadows the
built-in ``set`` type locally but that is intentional — callers should use
``Set[T]`` from ``typing`` instead of the built-in name inside this file.
"""
from __future__ import annotations

from typing import Callable, FrozenSet, Iterable, Iterator, Set, TypeVar

__all__ = [
    "difference",
    "intersects",
    "every",
    "union",
    "intersection",
    "symmetric_difference",
    "filter_set",
    "map_set",
    "flatten_sets",
    "is_disjoint",
    "is_subset",
    "is_superset",
]

T = TypeVar("T")
U = TypeVar("U")


def difference(a: Set[T], b: Set[T]) -> Set[T]:
    """Return elements in *a* that are not in *b* (set difference: a − b)."""
    return a - b


def intersects(a: Set[T], b: Set[T]) -> bool:
    """Return True if *a* and *b* share at least one element."""
    return not a.isdisjoint(b)


def every(a: Set[T], b: Set[T]) -> bool:
    """Return True if every element of *a* is also in *b* (a ⊆ b)."""
    return a.issubset(b)


def union(a: Set[T], b: Set[T]) -> Set[T]:
    """Return the union of *a* and *b* (a ∪ b)."""
    return a | b


def intersection(a: Set[T], b: Set[T]) -> Set[T]:
    """Return the intersection of *a* and *b* (a ∩ b)."""
    return a & b


def symmetric_difference(a: Set[T], b: Set[T]) -> Set[T]:
    """Return elements in exactly one of *a* or *b* (a △ b)."""
    return a ^ b


def filter_set(s: Set[T], predicate: Callable[[T], bool]) -> Set[T]:
    """Return elements of *s* that satisfy *predicate*."""
    return {x for x in s if predicate(x)}


def map_set(s: Set[T], fn: Callable[[T], U]) -> Set[U]:
    """Apply *fn* to each element and return the resulting set."""
    return {fn(x) for x in s}


def flatten_sets(sets: Iterable[Set[T]]) -> Set[T]:
    """Merge multiple sets into one."""
    result: Set[T] = set()
    for s in sets:
        result |= s
    return result


def is_disjoint(a: Set[T], b: Set[T]) -> bool:
    """Return True if *a* and *b* share no elements."""
    return a.isdisjoint(b)


def is_subset(a: Set[T], b: Set[T]) -> bool:
    """Return True if *a* is a subset of *b* (a ⊆ b)."""
    return a.issubset(b)


def is_superset(a: Set[T], b: Set[T]) -> bool:
    """Return True if *a* is a superset of *b* (a ⊇ b)."""
    return a.issuperset(b)

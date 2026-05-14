"""Set utilities. Ported from utils/set.ts and related helpers."""

from __future__ import annotations

from typing import Callable, FrozenSet, Iterable, Iterator, Set, TypeVar

T = TypeVar("T")
U = TypeVar("U")


def difference(a: Set[T], b: Set[T]) -> Set[T]:
    """Return elements in *a* that are not in *b*."""
    return {x for x in a if x not in b}


def intersects(a: Set[T], b: Set[T]) -> bool:
    """Return True if the two sets share at least one element."""
    if not a or not b:
        return False
    return any(x in b for x in a)


def every(a: Set[T], b: Set[T]) -> bool:
    """Return True if every element of *a* is also in *b* (a ⊆ b)."""
    return all(x in b for x in a)


def union(a: Set[T], b: Set[T]) -> Set[T]:
    """Return the union of two sets."""
    return a | b


def intersection(a: Set[T], b: Set[T]) -> Set[T]:
    """Return the intersection of two sets."""
    return a & b


def symmetric_difference(a: Set[T], b: Set[T]) -> Set[T]:
    """Return elements that are in exactly one of the two sets."""
    return a ^ b


def filter_set(s: Set[T], predicate: Callable[[T], bool]) -> Set[T]:
    """Return a new set containing only elements satisfying *predicate*."""
    return {x for x in s if predicate(x)}


def map_set(s: Set[T], fn: Callable[[T], U]) -> Set[U]:
    """Apply *fn* to each element and return the resulting set."""
    return {fn(x) for x in s}


def from_iterable(iterable: Iterable[T]) -> Set[T]:
    """Create a set from any iterable."""
    return set(iterable)


def is_disjoint(a: Set[T], b: Set[T]) -> bool:
    """Return True if *a* and *b* share no elements."""
    return a.isdisjoint(b)


def flatten(sets: Iterable[Set[T]]) -> Set[T]:
    """Merge multiple sets into one."""
    result: Set[T] = set()
    for s in sets:
        result |= s
    return result


def frozen_union(a: FrozenSet[T], b: FrozenSet[T]) -> FrozenSet[T]:
    """Return the frozen union of two frozen sets."""
    return a | b


def to_sorted_list(s: Set[T], key: Callable[[T], object] | None = None) -> list[T]:
    """Return a sorted list from a set, with optional key function."""
    return sorted(s, key=key)  # type: ignore[type-var]


def count_where(s: Set[T], predicate: Callable[[T], bool]) -> int:
    """Count elements in *s* satisfying *predicate*."""
    return sum(1 for x in s if predicate(x))

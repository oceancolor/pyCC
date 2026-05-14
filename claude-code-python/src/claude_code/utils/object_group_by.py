"""Object groupBy utility (TC39 proposal polyfill). Ported from objectGroupBy.ts.

Groups an iterable of values into a dict of lists, using a key selector
function to determine the group for each item.  Mirrors
``Object.groupBy`` (ECMAScript 2024) and ``Map.groupBy``.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Callable, Dict, Hashable, Iterable, Iterator, List, Mapping, TypeVar

__all__ = [
    "object_group_by",
    "map_group_by",
    "group_by_property",
    "partition",
]

K = TypeVar("K", bound=Hashable)
T = TypeVar("T")


def object_group_by(
    items: Iterable[T],
    key_selector: Callable[[T, int], K],
) -> Dict[K, List[T]]:
    """Group *items* into a dict of lists keyed by *key_selector(item, index)*.

    Mirrors ``Object.groupBy(items, keySelector)`` (ES2024).

    Example::

        result = object_group_by([1, 2, 3, 4], lambda x, _: "even" if x % 2 == 0 else "odd")
        # → {"odd": [1, 3], "even": [2, 4]}
    """
    result: Dict[K, List[T]] = defaultdict(list)
    for index, item in enumerate(items):
        key = key_selector(item, index)
        result[key].append(item)
    return dict(result)


def map_group_by(
    items: Iterable[T],
    key_selector: Callable[[T], K],
) -> Dict[K, List[T]]:
    """Like object_group_by but key_selector receives only the item (no index).

    Mirrors ``Map.groupBy(items, keySelector)`` (ES2024).
    """
    return object_group_by(items, lambda item, _: key_selector(item))


def group_by_property(items: Iterable[T], attr: str) -> Dict[object, List[T]]:
    """Group *items* by the value of attribute *attr* on each item."""
    return map_group_by(items, lambda item: getattr(item, attr, None))


def partition(items: Iterable[T], predicate: Callable[[T], bool]) -> tuple[List[T], List[T]]:
    """Split *items* into two lists: those matching *predicate* and those that don't.

    Returns ``(matching, non_matching)``.

    Example::

        evens, odds = partition([1, 2, 3, 4], lambda x: x % 2 == 0)
        # evens → [2, 4], odds → [1, 3]
    """
    matching: List[T] = []
    non_matching: List[T] = []
    for item in items:
        if predicate(item):
            matching.append(item)
        else:
            non_matching.append(item)
    return matching, non_matching

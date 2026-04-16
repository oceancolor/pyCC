"""
Object groupBy utility (TC39 proposal polyfill).
Port of utils/objectGroupBy.ts
"""
from collections import defaultdict
from typing import Callable, Dict, Hashable, Iterable, List, TypeVar

K = TypeVar("K", bound=Hashable)
T = TypeVar("T")


def object_group_by(
    items: Iterable[T],
    key_selector: Callable[[T, int], K],
) -> Dict[K, List[T]]:
    """Group items into a dict by the key returned by key_selector(item, index)."""
    result: Dict[K, List[T]] = defaultdict(list)
    for index, item in enumerate(items):
        key = key_selector(item, index)
        result[key].append(item)
    return dict(result)

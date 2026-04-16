"""Set utilities. Ported from set.ts"""
from __future__ import annotations
from typing import Set, TypeVar
T = TypeVar("T")

def difference(a: Set[T], b: Set[T]) -> Set[T]:
    return {x for x in a if x not in b}

def intersects(a: Set[T], b: Set[T]) -> bool:
    if not a or not b:
        return False
    return any(x in b for x in a)

def every(a: Set[T], b: Set[T]) -> bool:
    return all(x in b for x in a)

def union(a: Set[T], b: Set[T]) -> Set[T]:
    return a | b

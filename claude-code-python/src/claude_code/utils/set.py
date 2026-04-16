"""Set utility functions. Ported from utils/set.ts"""
from __future__ import annotations
from typing import TypeVar, Set

T = TypeVar("T")


def difference(a: Set[T], b: Set[T]) -> Set[T]:
    return a - b


def intersects(a: Set[T], b: Set[T]) -> bool:
    return not a.isdisjoint(b)


def every(a: Set[T], b: Set[T]) -> bool:
    return a.issubset(b)


def union(a: Set[T], b: Set[T]) -> Set[T]:
    return a | b

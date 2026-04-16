# 原始 TS: utils/CircularBuffer.ts
"""固定容量循环缓冲区"""
from typing import Generic, TypeVar, List, Iterator

T = TypeVar("T")


class CircularBuffer(Generic[T]):
    """固定容量的循环缓冲区，满后覆盖最旧元素"""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be > 0")
        self._capacity = capacity
        self._buf: List[T] = []
        self._start = 0

    def push(self, item: T) -> None:
        if len(self._buf) < self._capacity:
            self._buf.append(item)
        else:
            self._buf[self._start] = item
            self._start = (self._start + 1) % self._capacity

    def __iter__(self) -> Iterator[T]:
        n = len(self._buf)
        for i in range(n):
            yield self._buf[(self._start + i) % n]

    def __len__(self) -> int:
        return len(self._buf)

    def to_list(self) -> List[T]:
        return list(self)

    @property
    def capacity(self) -> int:
        return self._capacity

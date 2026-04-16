# 原始 TS: utils/earlyInput.ts
"""提前输入缓冲（用户在 agent 还在思考时输入的内容）"""
from __future__ import annotations
from typing import List, Optional


class EarlyInputBuffer:
    """
    缓冲用户在 agent 处理中输入的文字。
    agent 空闲后一次性处理。
    """
    def __init__(self) -> None:
        self._buffer: List[str] = []
        self._locked = False

    def lock(self) -> None:
        """agent 开始处理，锁住输入"""
        self._locked = True

    def unlock(self) -> None:
        """agent 空闲，解锁"""
        self._locked = False

    def push(self, text: str) -> None:
        if self._locked:
            self._buffer.append(text)

    def pop_all(self) -> List[str]:
        items = list(self._buffer)
        self._buffer.clear()
        return items

    def peek(self) -> Optional[str]:
        return self._buffer[0] if self._buffer else None

    def has_pending(self) -> bool:
        return bool(self._buffer)

    @property
    def is_locked(self) -> bool:
        return self._locked


_buffer = EarlyInputBuffer()

def get_early_input_buffer() -> EarlyInputBuffer:
    return _buffer

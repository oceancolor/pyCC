# 原始 TS: utils/cleanupRegistry.ts
"""清理处理器注册（带优先级）"""
from __future__ import annotations
import atexit
from typing import Callable, List, Tuple

_handlers: List[Tuple[int, Callable]] = []  # (priority, fn)
_registered = False


def register(fn: Callable, priority: int = 0) -> None:
    """注册清理函数，priority 越大越先执行"""
    global _registered
    _handlers.append((priority, fn))
    if not _registered:
        atexit.register(_run_all)
        _registered = True


def _run_all() -> None:
    for _, fn in sorted(_handlers, key=lambda x: -x[0]):
        try:
            fn()
        except Exception:
            pass


def clear() -> None:
    _handlers.clear()

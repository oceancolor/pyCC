# 原始 TS: utils/commandLifecycle.ts
"""命令生命周期管理：before/after 钩子、错误处理"""
from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator, Callable, Optional


@asynccontextmanager
async def command_lifecycle(
    command_name: str,
    on_start: Optional[Callable[[str], Any]] = None,
    on_end: Optional[Callable[[str, float, Optional[Exception]], Any]] = None,
) -> AsyncGenerator[None, None]:
    """
    异步命令生命周期上下文管理器。

    Usage:
        async with command_lifecycle("my_command") as _:
            await do_work()
    """
    start = time.monotonic()
    if on_start:
        on_start(command_name)
    exc: Optional[Exception] = None
    try:
        yield
    except Exception as e:
        exc = e
        raise
    finally:
        elapsed = time.monotonic() - start
        if on_end:
            on_end(command_name, elapsed, exc)


def default_on_start(name: str) -> None:
    pass  # 可以接入日志


def default_on_end(name: str, elapsed: float, exc: Optional[Exception]) -> None:
    if exc:
        pass  # TODO: log error

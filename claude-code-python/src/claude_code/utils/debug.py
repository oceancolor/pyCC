# 原始 TS: utils/debug.ts / utils/debugFilter.ts
"""调试日志工具"""
from __future__ import annotations
import os
import sys
import time
from typing import Any

_DEBUG_ENABLED = os.environ.get("CLAUDE_DEBUG", "").lower() in ("1", "true")
_DEBUG_FILTER = os.environ.get("CLAUDE_DEBUG_FILTER", "")  # 逗号分隔的命名空间


def is_debug() -> bool:
    return _DEBUG_ENABLED


def debug(namespace: str, *args: Any) -> None:
    if not _DEBUG_ENABLED:
        return
    if _DEBUG_FILTER and namespace not in _DEBUG_FILTER.split(","):
        return
    ts = time.strftime("%H:%M:%S")
    msg = " ".join(str(a) for a in args)
    print(f"\033[2m[{ts}][{namespace}] {msg}\033[0m", file=sys.stderr)


def debug_log(msg: str, **kwargs: Any) -> None:
    if not _DEBUG_ENABLED:
        return
    extra = " ".join(f"{k}={v}" for k, v in kwargs.items())
    ts = time.strftime("%H:%M:%S")
    print(f"\033[2m[{ts}] {msg} {extra}\033[0m", file=sys.stderr)

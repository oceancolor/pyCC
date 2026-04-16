# 原始 TS: utils/isSingleTurnMode.ts / utils/isHeadlessMode.ts
"""运行模式检测"""
from __future__ import annotations
import os
import sys


def is_single_turn_mode() -> bool:
    """是否为单轮模式（--print / -p 标志）"""
    return "--print" in sys.argv or "-p" in sys.argv


def is_headless_mode() -> bool:
    """是否为无头模式（非交互，CI/CD 环境）"""
    return (
        not sys.stdin.isatty()
        or os.environ.get("CI", "") != ""
        or os.environ.get("CLAUDE_HEADLESS", "") in ("1", "true")
    )


def is_interactive() -> bool:
    return sys.stdin.isatty() and not is_single_turn_mode() and not is_headless_mode()


def get_run_mode() -> str:
    if is_single_turn_mode():
        return "single-turn"
    if is_headless_mode():
        return "headless"
    return "interactive"

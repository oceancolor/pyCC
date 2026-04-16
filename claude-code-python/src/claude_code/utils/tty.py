# 原始 TS: utils/tty.ts
"""TTY 检测与终端大小"""
from __future__ import annotations
import os
import shutil
import sys
from typing import Tuple


def is_tty() -> bool:
    return sys.stdout.isatty()


def get_terminal_size() -> Tuple[int, int]:
    """返回 (columns, lines)"""
    size = shutil.get_terminal_size((80, 24))
    return size.columns, size.lines


def get_terminal_width() -> int:
    return get_terminal_size()[0]


def supports_color() -> bool:
    """检测终端是否支持颜色"""
    if not is_tty():
        return False
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    term = os.environ.get("TERM", "")
    return "color" in term or term in ("xterm-256color", "screen-256color", "xterm")


def clear_line() -> str:
    return "\r\033[K"


def move_up(n: int = 1) -> str:
    return f"\033[{n}A"


def hide_cursor() -> str:
    return "\033[?25l"


def show_cursor() -> str:
    return "\033[?25h"

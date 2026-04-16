# 原始 TS: keybindings/types.ts
"""键绑定类型定义"""
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional


class KeyAction(str, Enum):
    SUBMIT = "submit"
    NEWLINE = "newline"
    ABORT = "abort"
    CLEAR = "clear"
    HISTORY_UP = "history_up"
    HISTORY_DOWN = "history_down"
    COMPACT = "compact"
    PASTE = "paste"
    AUTOCOMPLETE = "autocomplete"
    FOCUS_NEXT = "focus_next"
    FOCUS_PREV = "focus_prev"
    QUIT = "quit"


@dataclass
class KeyBinding:
    key: str          # e.g. "ctrl+c", "enter", "escape"
    action: KeyAction
    description: str = ""
    handler: Optional[Callable] = None

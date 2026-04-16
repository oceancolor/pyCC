# 原始 TS: utils/vim.ts / utils/viMode.ts
"""Vi/Vim 模式支持（REPL 中的 vi 键绑定）"""
from __future__ import annotations
from enum import Enum
from typing import Optional


class ViMode(str, Enum):
    NORMAL = "normal"
    INSERT = "insert"
    VISUAL = "visual"
    COMMAND = "command"


class ViState:
    def __init__(self) -> None:
        self._mode = ViMode.INSERT  # REPL 默认 insert 模式
        self._pending_cmd = ""

    @property
    def mode(self) -> ViMode:
        return self._mode

    def set_mode(self, mode: ViMode) -> None:
        self._mode = mode
        self._pending_cmd = ""

    def is_insert(self) -> bool:
        return self._mode == ViMode.INSERT

    def is_normal(self) -> bool:
        return self._mode == ViMode.NORMAL

    def enter_insert(self) -> None:
        self._mode = ViMode.INSERT

    def enter_normal(self) -> None:
        self._mode = ViMode.NORMAL

    def mode_indicator(self) -> str:
        indicators = {
            ViMode.NORMAL: "NORMAL",
            ViMode.INSERT: "INSERT",
            ViMode.VISUAL: "VISUAL",
            ViMode.COMMAND: "COMMAND",
        }
        return indicators.get(self._mode, "")


def is_vi_mode_enabled() -> bool:
    import os
    return os.environ.get("CLAUDE_VI_MODE", "").lower() in ("1", "true")

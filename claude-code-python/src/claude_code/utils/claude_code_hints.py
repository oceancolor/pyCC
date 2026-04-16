# 原始 TS: utils/claudeCodeHints.ts
"""Claude Code 使用提示（首次使用引导）"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import List, Optional

_HINTS_FILE = Path.home() / ".claude" / ".hints_shown"

HINTS: List[dict] = [
    {"id": "help",     "text": "输入 /help 查看所有可用命令"},
    {"id": "clear",    "text": "输入 /clear 清除对话历史"},
    {"id": "compact",  "text": "对话太长时输入 /compact 压缩历史"},
    {"id": "files",    "text": "可以直接问「帮我看看 main.py 有什么问题」"},
    {"id": "tools",    "text": "Claude 可以执行 bash 命令、读写文件、搜索代码"},
]


def _load_shown() -> set:
    if _HINTS_FILE.exists():
        try:
            return set(json.loads(_HINTS_FILE.read_text()))
        except Exception:
            pass
    return set()


def _save_shown(shown: set) -> None:
    _HINTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    _HINTS_FILE.write_text(json.dumps(list(shown)))


def get_next_hint() -> Optional[str]:
    shown = _load_shown()
    for h in HINTS:
        if h["id"] not in shown:
            shown.add(h["id"])
            _save_shown(shown)
            return h["text"]
    return None


def mark_all_shown() -> None:
    _save_shown({h["id"] for h in HINTS})

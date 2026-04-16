# 原始 TS: utils/fileHistory.ts
"""文件编辑历史（撤销支持）"""
from __future__ import annotations
from collections import defaultdict
from typing import Dict, List, Optional


class FileHistory:
    """记录文件的编辑历史，支持撤销"""

    def __init__(self, max_history: int = 50) -> None:
        self._history: Dict[str, List[str]] = defaultdict(list)
        self._max = max_history

    def snapshot(self, path: str, content: str) -> None:
        hist = self._history[path]
        if hist and hist[-1] == content:
            return
        hist.append(content)
        if len(hist) > self._max:
            hist.pop(0)

    def undo(self, path: str) -> Optional[str]:
        hist = self._history[path]
        if len(hist) < 2:
            return None
        hist.pop()
        return hist[-1]

    def get_latest(self, path: str) -> Optional[str]:
        hist = self._history.get(path)
        return hist[-1] if hist else None

    def clear(self, path: Optional[str] = None) -> None:
        if path:
            self._history.pop(path, None)
        else:
            self._history.clear()


_history = FileHistory()

def get_file_history() -> FileHistory:
    return _history

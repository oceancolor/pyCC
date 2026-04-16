# 原始 TS: utils/logTailManager.ts
"""日志尾部管理（流式追加写入，限制大小）"""
from __future__ import annotations
import threading
import time
from pathlib import Path
from typing import List, Optional


class LogTailManager:
    """线程安全的日志尾部写入器，保留最后 N 行"""

    def __init__(self, path: Path, max_lines: int = 1000) -> None:
        self._path = path
        self._max_lines = max_lines
        self._lock = threading.Lock()
        self._buffer: List[str] = []
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, line: str) -> None:
        ts = time.strftime("%H:%M:%S")
        entry = f"[{ts}] {line}"
        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > self._max_lines:
                self._buffer = self._buffer[-self._max_lines:]

    def flush(self) -> None:
        with self._lock:
            if not self._buffer:
                return
            content = "\n".join(self._buffer) + "\n"
            self._path.write_text(content)

    def tail(self, n: int = 50) -> List[str]:
        with self._lock:
            return self._buffer[-n:]

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()

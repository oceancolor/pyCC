# 原始 TS: utils/fileReadCache.ts / utils/fileStateCache.ts
"""文件读取缓存（避免重复磁盘 I/O）"""
from __future__ import annotations
import hashlib
import os
import time
from typing import Dict, Optional, Tuple


class FileReadCache:
    """缓存文件内容，按 mtime+size 失效"""

    def __init__(self, max_size: int = 200) -> None:
        self._cache: Dict[str, Tuple[float, int, str]] = {}  # path -> (mtime, size, content)
        self._max_size = max_size

    def get(self, path: str) -> Optional[str]:
        entry = self._cache.get(path)
        if entry is None:
            return None
        try:
            stat = os.stat(path)
            if stat.st_mtime == entry[0] and stat.st_size == entry[1]:
                return entry[2]
        except OSError:
            pass
        del self._cache[path]
        return None

    def set(self, path: str, content: str) -> None:
        if len(self._cache) >= self._max_size:
            oldest = next(iter(self._cache))
            del self._cache[oldest]
        try:
            stat = os.stat(path)
            self._cache[path] = (stat.st_mtime, stat.st_size, content)
        except OSError:
            pass

    def read(self, path: str, encoding: str = "utf-8") -> str:
        cached = self.get(path)
        if cached is not None:
            return cached
        content = open(path, encoding=encoding, errors="replace").read()
        self.set(path, content)
        return content

    def invalidate(self, path: str) -> None:
        self._cache.pop(path, None)

    def clear(self) -> None:
        self._cache.clear()


_default_cache = FileReadCache()

def get_file_cache() -> FileReadCache:
    return _default_cache

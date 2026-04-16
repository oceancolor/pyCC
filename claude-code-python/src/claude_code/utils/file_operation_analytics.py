# 原始 TS: utils/fileOperationAnalytics.ts
"""文件操作分析（统计读写次数，检测重复操作）"""
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class FileOpStats:
    reads: int = 0
    writes: int = 0
    edits: int = 0
    errors: int = 0

    @property
    def total(self) -> int:
        return self.reads + self.writes + self.edits


class FileOperationAnalytics:
    def __init__(self) -> None:
        self._stats: Dict[str, FileOpStats] = defaultdict(FileOpStats)
        self._recent: List[tuple] = []  # (op, path)

    def record(self, op: str, path: str, error: bool = False) -> None:
        s = self._stats[path]
        if error:
            s.errors += 1
        elif op == "read":
            s.reads += 1
        elif op == "write":
            s.writes += 1
        elif op == "edit":
            s.edits += 1
        self._recent.append((op, path))
        if len(self._recent) > 500:
            self._recent.pop(0)

    def get_stats(self, path: str) -> FileOpStats:
        return self._stats.get(path, FileOpStats())

    def most_accessed(self, n: int = 10) -> List[tuple]:
        return sorted(
            self._stats.items(),
            key=lambda x: x[1].total,
            reverse=True,
        )[:n]

    def summary(self) -> str:
        total_ops = sum(s.total for s in self._stats.values())
        return f"文件操作: {total_ops} 次，涉及 {len(self._stats)} 个文件"


_analytics = FileOperationAnalytics()

def get_file_analytics() -> FileOperationAnalytics:
    return _analytics

# 原始 TS: utils/fileRead.ts / utils/fileReadOptimized.ts
"""优化的文件读取（带大小限制和编码检测）"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Tuple

MAX_READ_BYTES = 10 * 1024 * 1024  # 10MB
MAX_DISPLAY_LINES = 2000


def read_file_safe(path: str, max_bytes: int = MAX_READ_BYTES) -> Tuple[str, bool]:
    """安全读取文件，返回 (content, truncated)"""
    p = Path(path)
    size = p.stat().st_size
    truncated = size > max_bytes
    with open(path, "rb") as f:
        raw = f.read(max_bytes)
    try:
        return raw.decode("utf-8"), truncated
    except UnicodeDecodeError:
        try:
            return raw.decode("latin-1"), truncated
        except Exception:
            return raw.decode("utf-8", errors="replace"), truncated


def read_file_lines(path: str, start: int = 1, end: Optional[int] = None) -> str:
    """读取文件指定行范围（1-indexed）"""
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    s = max(0, start - 1)
    e = end if end else len(lines)
    selected = lines[s:e]
    return "".join(selected)


def is_binary_file(path: str, sample_size: int = 8192) -> bool:
    """检测文件是否为二进制"""
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
        return b"\x00" in chunk
    except OSError:
        return False


def get_file_info(path: str) -> dict:
    """获取文件元信息"""
    p = Path(path)
    stat = p.stat()
    return {
        "path": str(p.resolve()),
        "size": stat.st_size,
        "lines": sum(1 for _ in open(path, "rb")),
        "is_binary": is_binary_file(path),
        "extension": p.suffix,
    }

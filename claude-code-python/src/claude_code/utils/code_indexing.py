# 原始 TS: utils/codeIndexing.ts
"""代码索引工具（文件树快照，供 context 注入）"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional, Set

IGNORED_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
                ".next", ".nuxt", "coverage", ".coverage", "target", ".cargo"}
IGNORED_EXTS = {".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe", ".bin",
                ".jpg", ".jpeg", ".png", ".gif", ".webp", ".ico",
                ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z",
                ".pdf", ".doc", ".docx", ".xls", ".xlsx"}
MAX_FILES = 1000


def build_file_tree(root: str, max_depth: int = 5) -> str:
    """生成目录树字符串（用于注入到 system prompt）"""
    lines: List[str] = []
    count = 0

    def _walk(path: Path, depth: int, prefix: str) -> None:
        nonlocal count
        if depth > max_depth or count >= MAX_FILES:
            return
        try:
            entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for i, entry in enumerate(entries):
            if entry.name in IGNORED_DIRS or entry.name.startswith("."):
                continue
            if entry.is_file() and entry.suffix in IGNORED_EXTS:
                continue
            is_last = (i == len(entries) - 1)
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}")
            count += 1
            if count >= MAX_FILES:
                lines.append(f"{prefix}    ... (truncated)")
                return
            if entry.is_dir() and entry.name not in IGNORED_DIRS:
                extension = "    " if is_last else "│   "
                _walk(entry, depth + 1, prefix + extension)

    root_path = Path(root)
    lines.append(root_path.name + "/")
    _walk(root_path, 0, "")
    return "\n".join(lines)


def get_relevant_files(root: str, extensions: Optional[List[str]] = None) -> List[str]:
    """返回项目中所有相关代码文件路径"""
    exts = set(extensions or [".py", ".ts", ".js", ".tsx", ".jsx", ".go", ".rs", ".java"])
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for fname in filenames:
            if Path(fname).suffix in exts:
                result.append(os.path.join(dirpath, fname))
            if len(result) >= MAX_FILES:
                return result
    return result

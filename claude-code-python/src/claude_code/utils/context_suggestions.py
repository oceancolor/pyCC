# 原始 TS: utils/contextSuggestions.ts
"""Context 建议（建议用户引用相关文件）"""
from __future__ import annotations
import os
from pathlib import Path
from typing import List, Optional
from .detect_repository import find_git_root
from .code_indexing import IGNORED_DIRS, IGNORED_EXTS


def suggest_related_files(query: str, cwd: Optional[str] = None, limit: int = 5) -> List[str]:
    """根据查询关键词推荐相关文件"""
    root = find_git_root(cwd) or (cwd or os.getcwd())
    keywords = query.lower().split()
    matches: List[tuple] = []

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORED_DIRS and not d.startswith(".")]
        for fname in filenames:
            if Path(fname).suffix in IGNORED_EXTS:
                continue
            score = sum(1 for kw in keywords if kw in fname.lower())
            if score > 0:
                matches.append((score, os.path.join(dirpath, fname)))

    matches.sort(key=lambda x: -x[0])
    return [m[1] for m in matches[:limit]]


def format_suggestions(files: List[str], cwd: str = "") -> str:
    if not files:
        return ""
    rel = [os.path.relpath(f, cwd) if cwd else f for f in files]
    lines = ["相关文件建议："] + [f"  - {f}" for f in rel]
    return "\n".join(lines)

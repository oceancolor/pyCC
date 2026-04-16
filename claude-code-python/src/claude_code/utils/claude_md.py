# 原始 TS: utils/claudemd.ts
"""CLAUDE.md 文件读取与处理（项目级 AI 指令文件）"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


CLAUDE_MD_FILENAMES = ["CLAUDE.md", "claude.md", ".claude.md", "CLAUDE.local.md"]


def find_claude_md(start_dir: Optional[str] = None) -> List[Path]:
    """
    从给定目录向上搜索 CLAUDE.md 文件。
    返回从根到当前目录的所有找到的文件（从远到近）。
    """
    start = Path(start_dir or os.getcwd()).resolve()
    found: List[Path] = []

    current = start
    while True:
        for name in CLAUDE_MD_FILENAMES:
            candidate = current / name
            if candidate.exists():
                found.append(candidate)
        parent = current.parent
        if parent == current:
            break
        current = parent

    return list(reversed(found))  # 从根到当前


def read_claude_md(start_dir: Optional[str] = None) -> Optional[str]:
    """读取项目中的 CLAUDE.md 内容，多个文件合并"""
    files = find_claude_md(start_dir)
    if not files:
        return None
    parts = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8").strip()
            if content:
                parts.append(f"# From {f}\n{content}")
        except OSError:
            pass
    return "\n\n".join(parts) if parts else None


def build_system_prompt_with_claude_md(base_prompt: str, cwd: Optional[str] = None) -> str:
    """将 CLAUDE.md 内容注入 system prompt"""
    claude_md = read_claude_md(cwd)
    if claude_md:
        return f"{base_prompt}\n\n---\n{claude_md}"
    return base_prompt

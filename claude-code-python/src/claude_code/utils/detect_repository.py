# 原始 TS: utils/detectRepository.ts
"""代码仓库检测（git, hg, svn 等）"""
from __future__ import annotations
import os
import subprocess
from pathlib import Path
from typing import Optional


def find_git_root(start: Optional[str] = None) -> Optional[str]:
    """从 start 目录向上找 .git"""
    current = Path(start or os.getcwd()).resolve()
    while True:
        if (current / ".git").exists():
            return str(current)
        parent = current.parent
        if parent == current:
            return None
        current = parent


def get_repo_info(cwd: Optional[str] = None) -> dict:
    """获取当前仓库信息"""
    root = find_git_root(cwd)
    if not root:
        return {"type": None, "root": None}
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        remote = None
    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        branch = None
    return {"type": "git", "root": root, "remote": remote, "branch": branch}


def is_in_repo(cwd: Optional[str] = None) -> bool:
    return find_git_root(cwd) is not None

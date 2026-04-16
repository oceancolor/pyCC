# 原始 TS: utils/findExecutable.ts
"""查找可执行文件（跨平台）"""
from __future__ import annotations
import os
import shutil
import sys
from typing import List, Optional


def find_executable(name: str, extra_paths: Optional[List[str]] = None) -> Optional[str]:
    """在 PATH 及 extra_paths 中搜索可执行文件"""
    if extra_paths:
        old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join(extra_paths) + os.pathsep + old_path
        result = shutil.which(name)
        os.environ["PATH"] = old_path
        return result
    return shutil.which(name)


def find_node() -> Optional[str]:
    return find_executable("node")


def find_python() -> Optional[str]:
    for candidate in ("python3", "python"):
        path = find_executable(candidate)
        if path:
            return path
    return sys.executable


def find_git() -> Optional[str]:
    return find_executable("git")


def find_ripgrep() -> Optional[str]:
    for candidate in ("rg", "ripgrep"):
        path = find_executable(candidate)
        if path:
            return path
    return None

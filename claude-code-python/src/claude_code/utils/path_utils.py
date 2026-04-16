# 原始 TS: utils/pathUtils.ts（路径工具扩展）
"""路径工具扩展"""
from __future__ import annotations
import os
from pathlib import Path
from typing import List, Optional


def expand_path(path: str) -> str:
    """展开 ~ 和环境变量"""
    return os.path.expandvars(os.path.expanduser(path))


def make_relative(path: str, base: Optional[str] = None) -> str:
    try:
        return os.path.relpath(path, base or os.getcwd())
    except ValueError:
        return path


def is_subpath(child: str, parent: str) -> bool:
    """判断 child 是否在 parent 目录下"""
    try:
        Path(child).resolve().relative_to(Path(parent).resolve())
        return True
    except ValueError:
        return False


def safe_join(*parts: str) -> str:
    """安全路径拼接（防止路径穿越）"""
    base = Path(parts[0]).resolve()
    result = base
    for part in parts[1:]:
        # 去掉 part 开头的 /
        clean = part.lstrip("/\\")
        result = (result / clean).resolve()
    # 确保没有逃出 base
    if not str(result).startswith(str(base)):
        raise ValueError(f"Path traversal detected: {result}")
    return str(result)


def get_file_extension(path: str) -> str:
    return Path(path).suffix.lower()


def strip_extension(path: str) -> str:
    return str(Path(path).with_suffix(""))


def list_files_recursive(root: str, extensions: Optional[List[str]] = None) -> List[str]:
    result = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if extensions is None or Path(f).suffix.lower() in extensions:
                result.append(os.path.join(dirpath, f))
    return result

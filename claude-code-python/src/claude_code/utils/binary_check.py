# 原始 TS: utils/binaryCheck.ts
"""检查系统中可执行文件是否存在"""
from __future__ import annotations
import shutil
from typing import Dict, Optional


_cache: Dict[str, Optional[str]] = {}


def find_binary(name: str) -> Optional[str]:
    if name not in _cache:
        _cache[name] = shutil.which(name)
    return _cache[name]


def is_available(name: str) -> bool:
    return find_binary(name) is not None


def require_binary(name: str) -> str:
    path = find_binary(name)
    if path is None:
        raise FileNotFoundError(f"Required binary not found: {name}")
    return path


def check_binaries(*names: str) -> Dict[str, bool]:
    return {name: is_available(name) for name in names}

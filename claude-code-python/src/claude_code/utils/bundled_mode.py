# 原始 TS: utils/bundledMode.ts
"""打包模式检测（是否在打包/编译后的环境中运行）"""
from __future__ import annotations
import os
import sys


def is_bundled_mode() -> bool:
    """是否以打包后的二进制运行（PyInstaller/Nuitka 等）"""
    return getattr(sys, "frozen", False) or os.environ.get("CLAUDE_BUNDLED", "") in ("1", "true")


def get_bundle_dir() -> str:
    """获取打包后的目录"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def is_dev_mode() -> bool:
    return not is_bundled_mode() and os.environ.get("CLAUDE_DEV", "") in ("1", "true")

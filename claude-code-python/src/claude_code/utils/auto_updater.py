# 原始 TS: utils/autoUpdater.ts
"""自动更新检查（检查 PyPI 是否有新版本）"""
from __future__ import annotations

import json
from typing import Optional
from urllib.request import urlopen
from urllib.error import URLError

from .._version import __version__

PYPI_URL = "https://pypi.org/pypi/claude-code/json"
_cached_latest: Optional[str] = None


def _version_tuple(v: str):
    try:
        return tuple(int(x) for x in v.split(".")[:3])
    except ValueError:
        return (0, 0, 0)


def check_for_update(timeout: float = 3.0) -> Optional[str]:
    """
    检查 PyPI 是否有新版本。
    返回最新版本号字符串（如果有更新），否则返回 None。
    """
    global _cached_latest
    if _cached_latest is not None:
        return _cached_latest if _version_tuple(_cached_latest) > _version_tuple(__version__) else None
    try:
        with urlopen(PYPI_URL, timeout=timeout) as resp:
            data = json.load(resp)
            latest = data["info"]["version"]
            _cached_latest = latest
            if _version_tuple(latest) > _version_tuple(__version__):
                return latest
    except (URLError, KeyError, json.JSONDecodeError, OSError):
        pass
    return None


def get_update_message() -> Optional[str]:
    latest = check_for_update()
    if latest:
        return f"⬆ 新版本可用：{latest}（当前：{__version__}）运行 `pip install -U claude-code` 更新"
    return None

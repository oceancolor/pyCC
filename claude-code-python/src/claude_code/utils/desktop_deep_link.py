# 原始 TS: utils/desktopDeepLink.ts
"""Desktop deep link 处理（claude:// URL scheme）"""
from __future__ import annotations
import os
import re
from typing import Optional
from urllib.parse import urlparse, parse_qs


SCHEME = "claude"


def parse_deep_link(url: str) -> Optional[dict]:
    """解析 claude:// 深度链接"""
    try:
        parsed = urlparse(url)
        if parsed.scheme != SCHEME:
            return None
        params = parse_qs(parsed.query)
        return {
            "action": parsed.netloc or parsed.path.lstrip("/"),
            "params": {k: v[0] for k, v in params.items()},
            "raw": url,
        }
    except Exception:
        return None


def build_deep_link(action: str, **params: str) -> str:
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{SCHEME}://{action}{'?' + query if query else ''}"


def is_deep_link(url: str) -> bool:
    return url.startswith(f"{SCHEME}://")

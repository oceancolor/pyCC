# 原始 TS: utils/apiPreconnect.ts
"""API 预连接（提前建立连接，减少首次请求延迟）"""
from __future__ import annotations
import asyncio
import os
from typing import Optional

_preconnected = False


async def preconnect_api(timeout: float = 3.0) -> bool:
    """预连接到 Anthropic API（HEAD 请求）"""
    global _preconnected
    if _preconnected:
        return True
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.anthropic.com",
            method="HEAD",
            headers={"User-Agent": "claude-code-python/preconnect"},
        )
        loop = asyncio.get_event_loop()
        await asyncio.wait_for(
            loop.run_in_executor(None, lambda: urllib.request.urlopen(req, timeout=timeout)),
            timeout=timeout,
        )
        _preconnected = True
        return True
    except Exception:
        return False


def is_preconnected() -> bool:
    return _preconnected

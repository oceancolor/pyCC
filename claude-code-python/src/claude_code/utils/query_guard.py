# 原始 TS: utils/queryGuard.ts
"""查询守卫（防止并发重复查询、请求去重）"""
from __future__ import annotations
import asyncio
import hashlib
import json
from typing import Any, Callable, Coroutine, Dict, Optional


class QueryGuard:
    """确保同一 key 的查询只执行一次，重复请求等待第一次结果"""

    def __init__(self) -> None:
        self._in_flight: Dict[str, asyncio.Future] = {}

    def _make_key(self, *args: Any) -> str:
        raw = json.dumps(args, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    async def deduplicate(self, key: str,
                          fn: Callable[[], Coroutine[Any, Any, Any]]) -> Any:
        if key in self._in_flight:
            return await asyncio.shield(self._in_flight[key])
        loop = asyncio.get_event_loop()
        future: asyncio.Future = loop.create_future()
        self._in_flight[key] = future
        try:
            result = await fn()
            future.set_result(result)
            return result
        except Exception as e:
            future.set_exception(e)
            raise
        finally:
            self._in_flight.pop(key, None)

    def is_in_flight(self, key: str) -> bool:
        return key in self._in_flight

    def cancel_all(self) -> None:
        for f in self._in_flight.values():
            if not f.done():
                f.cancel()
        self._in_flight.clear()

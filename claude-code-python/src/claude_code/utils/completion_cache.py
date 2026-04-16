# 原始 TS: utils/completionCache.ts
"""补全缓存：缓存模型响应避免重复调用"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Dict, Optional


class CompletionCache:
    """内存中的 LRU 风格补全缓存"""

    def __init__(self, max_size: int = 100, ttl_seconds: float = 3600) -> None:
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._max_size = max_size
        self._ttl = ttl_seconds

    def _key(self, model: str, messages: Any, **kwargs: Any) -> str:
        payload = json.dumps({"model": model, "messages": messages, **kwargs}, sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def get(self, model: str, messages: Any, **kwargs: Any) -> Optional[str]:
        key = self._key(model, messages, **kwargs)
        entry = self._cache.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry["ts"] > self._ttl:
            del self._cache[key]
            return None
        return entry["response"]

    def set(self, model: str, messages: Any, response: str, **kwargs: Any) -> None:
        key = self._key(model, messages, **kwargs)
        if len(self._cache) >= self._max_size:
            # 删除最旧的
            oldest = min(self._cache, key=lambda k: self._cache[k]["ts"])
            del self._cache[oldest]
        self._cache[key] = {"response": response, "ts": time.monotonic()}

    def clear(self) -> None:
        self._cache.clear()

    def __len__(self) -> int:
        return len(self._cache)


_default_cache = CompletionCache()


def get_cache() -> CompletionCache:
    return _default_cache

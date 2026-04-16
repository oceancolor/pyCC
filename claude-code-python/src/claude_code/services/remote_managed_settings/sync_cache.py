"""Remote settings sync cache. Stub."""
from __future__ import annotations
_cache: dict = {}
def get_cache() -> dict: return dict(_cache)
def set_cache(key: str, value: object) -> None: _cache[key] = value

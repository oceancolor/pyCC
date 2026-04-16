# 原始 TS: utils/uuid.ts
"""UUID 生成工具"""
from __future__ import annotations
import uuid


def new_uuid() -> str:
    return str(uuid.uuid4())


def short_uuid(length: int = 8) -> str:
    return str(uuid.uuid4()).replace("-", "")[:length]


def is_valid_uuid(s: str) -> bool:
    try:
        uuid.UUID(s)
        return True
    except ValueError:
        return False

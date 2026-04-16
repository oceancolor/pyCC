# 原始 TS: utils/agentId.ts
"""Agent ID 生成与管理"""
from __future__ import annotations
import os
import uuid
from pathlib import Path

_AGENT_ID_FILE = Path.home() / ".claude" / "agent_id"


def get_or_create_agent_id() -> str:
    """获取或创建持久化 agent ID"""
    if _AGENT_ID_FILE.exists():
        aid = _AGENT_ID_FILE.read_text().strip()
        if aid:
            return aid
    aid = str(uuid.uuid4())
    _AGENT_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    _AGENT_ID_FILE.write_text(aid)
    return aid


def get_session_id() -> str:
    """生成单次 session ID（不持久化）"""
    return str(uuid.uuid4())


def short_id(full_id: str) -> str:
    return full_id[:8]

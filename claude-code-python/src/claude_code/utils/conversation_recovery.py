# 原始 TS: utils/conversationRecovery.ts
"""对话恢复：从磁盘恢复中断的 session"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional


_SESSIONS_DIR = Path.home() / ".claude" / "sessions"


def list_recoverable_sessions() -> List[Dict[str, Any]]:
    """列出可恢复的 session"""
    if not _SESSIONS_DIR.exists():
        return []
    sessions = []
    for p in sorted(_SESSIONS_DIR.glob("*.jsonl"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            lines = p.read_text().splitlines()
            if not lines:
                continue
            header = json.loads(lines[0])
            sessions.append({
                "session_id": header.get("session_id", p.stem),
                "title": header.get("title", "Untitled"),
                "message_count": len(lines) - 1,
                "path": str(p),
                "mtime": p.stat().st_mtime,
            })
        except (json.JSONDecodeError, OSError):
            continue
    return sessions


def load_session_messages(session_id: str) -> List[Dict[str, Any]]:
    """从磁盘加载 session 消息"""
    path = _SESSIONS_DIR / f"{session_id}.jsonl"
    if not path.exists():
        return []
    messages = []
    lines = path.read_text().splitlines()
    for line in lines[1:]:  # 跳过 header
        try:
            messages.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return messages


def get_latest_session_id() -> Optional[str]:
    """获取最近一次 session ID"""
    sessions = list_recoverable_sessions()
    if sessions:
        return sessions[0]["session_id"]
    return None

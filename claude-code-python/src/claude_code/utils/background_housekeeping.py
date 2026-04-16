# 原始 TS: utils/background/backgroundHousekeeping.ts
"""后台维护任务：定期清理、归档旧 session 等"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import List


_SESSIONS_DIR = Path.home() / ".claude" / "sessions"
MAX_SESSION_AGE_DAYS = 30
MAX_SESSION_COUNT = 100


async def cleanup_old_sessions() -> int:
    """清理超过 MAX_SESSION_AGE_DAYS 天的旧 session 文件，返回删除数量"""
    if not _SESSIONS_DIR.exists():
        return 0
    deleted = 0
    cutoff = time.time() - MAX_SESSION_AGE_DAYS * 86400
    files = sorted(_SESSIONS_DIR.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    # 保留最新 MAX_SESSION_COUNT 个，其余按时间删除
    to_delete: List[Path] = []
    if len(files) > MAX_SESSION_COUNT:
        to_delete.extend(files[: len(files) - MAX_SESSION_COUNT])
    for f in files:
        if f.stat().st_mtime < cutoff and f not in to_delete:
            to_delete.append(f)
    for f in to_delete:
        try:
            f.unlink()
            deleted += 1
        except OSError:
            pass
    return deleted


async def run_housekeeping() -> None:
    """执行所有后台维护任务"""
    await cleanup_old_sessions()
    # TODO: 其他后台任务（日志轮转、缓存清理等）

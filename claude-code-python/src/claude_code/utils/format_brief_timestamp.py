# 原始 TS: utils/formatBriefTimestamp.ts
"""简短时间戳格式化"""
from __future__ import annotations
import time
from datetime import datetime, timezone
from typing import Optional


def format_brief_timestamp(ts: Optional[float] = None) -> str:
    """格式化为简短时间戳，如 '14:32' 或 '04-08 14:32'"""
    t = datetime.fromtimestamp(ts or time.time())
    now = datetime.now()
    if t.date() == now.date():
        return t.strftime("%H:%M")
    return t.strftime("%m-%d %H:%M")


def format_elapsed(seconds: float) -> str:
    """格式化经过时间，如 '1m23s' '2h5m'"""
    s = int(seconds)
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def iso_timestamp(ts: Optional[float] = None) -> str:
    return datetime.fromtimestamp(ts or time.time(), tz=timezone.utc).isoformat()

# 原始 TS: utils/diagLogs.ts / utils/diagnosticTracking.ts
"""诊断日志（轻量级遥测，本地记录）"""
from __future__ import annotations
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_DIAG_FILE = Path.home() / ".claude" / "logs" / "diagnostics.jsonl"
_MAX_ENTRIES = 1000


def log_event(event_type: str, data: Optional[Dict[str, Any]] = None) -> None:
    """记录诊断事件"""
    try:
        _DIAG_FILE.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": time.time(),
            "type": event_type,
            **(data or {}),
        }
        with open(_DIAG_FILE, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def get_recent_events(n: int = 50) -> List[Dict[str, Any]]:
    if not _DIAG_FILE.exists():
        return []
    events = []
    try:
        for line in _DIAG_FILE.read_text().splitlines()[-n:]:
            events.append(json.loads(line))
    except Exception:
        pass
    return events


def log_session_start(session_id: str, model: str) -> None:
    log_event("session_start", {"session_id": session_id, "model": model})


def log_session_end(session_id: str, turns: int, tokens: int) -> None:
    log_event("session_end", {"session_id": session_id, "turns": turns, "tokens": tokens})


def log_tool_call(tool_name: str, duration_ms: float, success: bool) -> None:
    log_event("tool_call", {"tool": tool_name, "duration_ms": duration_ms, "success": success})

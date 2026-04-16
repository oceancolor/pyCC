# 原始 TS: utils/errorLogSink.ts
"""错误日志收集（写入 ~/.claude/logs/errors.log）"""
from __future__ import annotations
import traceback
import time
from pathlib import Path
from typing import Optional

_LOG_FILE = Path.home() / ".claude" / "logs" / "errors.log"
_MAX_SIZE = 1 * 1024 * 1024  # 1MB


def log_error(error: Exception, context: Optional[str] = None) -> None:
    try:
        _LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        # 轮转：超过 1MB 截断
        if _LOG_FILE.exists() and _LOG_FILE.stat().st_size > _MAX_SIZE:
            _LOG_FILE.write_text("")
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        tb = traceback.format_exc()
        entry = f"[{ts}] {context or ''}\n{type(error).__name__}: {error}\n{tb}\n---\n"
        with open(_LOG_FILE, "a") as f:
            f.write(entry)
    except Exception:
        pass  # 日志失败不影响主流程


def get_recent_errors(n: int = 20) -> str:
    if not _LOG_FILE.exists():
        return "(no errors logged)"
    lines = _LOG_FILE.read_text().splitlines()
    return "\n".join(lines[-n * 6:])  # 每条约6行


def clear_error_log() -> None:
    if _LOG_FILE.exists():
        _LOG_FILE.write_text("")

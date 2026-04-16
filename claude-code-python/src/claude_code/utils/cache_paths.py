# 原始 TS: utils/cachePaths.ts
"""缓存路径管理（~/.claude/cache/）"""
from __future__ import annotations

import os
from pathlib import Path


_CLAUDE_DIR = Path.home() / ".claude"


def get_cache_dir() -> Path:
    p = _CLAUDE_DIR / "cache"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_sessions_dir() -> Path:
    p = _CLAUDE_DIR / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_logs_dir() -> Path:
    p = _CLAUDE_DIR / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_settings_path() -> Path:
    return _CLAUDE_DIR / "settings.json"


def get_credentials_path() -> Path:
    return _CLAUDE_DIR / "credentials.json"


def get_history_path() -> Path:
    return _CLAUDE_DIR / "repl_history"


def ensure_claude_dir() -> Path:
    _CLAUDE_DIR.mkdir(parents=True, exist_ok=True)
    return _CLAUDE_DIR

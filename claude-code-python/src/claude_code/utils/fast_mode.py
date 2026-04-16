# 原始 TS: utils/fastMode.ts
"""Fast mode（关闭 thinking，提速）"""
from __future__ import annotations
import os


def is_fast_mode() -> bool:
    return os.environ.get("CLAUDE_CODE_SIMPLE", "").lower() in ("1", "true")


def is_thinking_disabled() -> bool:
    return (
        os.environ.get("CLAUDE_CODE_DISABLE_THINKING", "").lower() in ("1", "true")
        or is_fast_mode()
    )


def is_interleaved_thinking_disabled() -> bool:
    return os.environ.get("DISABLE_INTERLEAVED_THINKING", "").lower() in ("1", "true")


def is_compact_disabled() -> bool:
    return os.environ.get("DISABLE_COMPACT", "").lower() in ("1", "true")


def is_auto_compact_disabled() -> bool:
    return os.environ.get("DISABLE_AUTO_COMPACT", "").lower() in ("1", "true")

# 原始 TS: utils/env.ts / utils/envDynamic.ts / utils/envValidation.ts
"""环境变量读取、动态检测与校验"""
from __future__ import annotations
import os
from typing import Any, Dict, List, Optional


def get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(key, default)


def require_env(key: str) -> str:
    val = os.environ.get(key)
    if not val:
        raise EnvironmentError(f"Required environment variable not set: {key}")
    return val


def get_bool_env(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, "").lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


def get_int_env(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default


def validate_api_key(key: Optional[str] = None) -> bool:
    k = key or os.environ.get("ANTHROPIC_API_KEY", "")
    return bool(k and (k.startswith("sk-ant-") or k.startswith("sk-")))


def get_claude_env_snapshot() -> Dict[str, str]:
    """获取所有 CLAUDE_* 和 ANTHROPIC_* 环境变量"""
    return {k: v for k, v in os.environ.items()
            if k.startswith(("CLAUDE_", "ANTHROPIC_"))}

# 原始 TS: utils/model.ts（模型工具函数）
"""模型相关工具：获取、验证、比较模型"""
from __future__ import annotations
import os
from typing import List, Optional

KNOWN_MODELS: List[str] = [
    "claude-opus-4-5",
    "claude-sonnet-4-5",
    "claude-haiku-3-5",
    "claude-opus-4",
    "claude-sonnet-4",
    "claude-haiku-3",
    "claude-3-5-sonnet-20241022",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
]

_DEFAULT_MODEL = "claude-opus-4-5"
_DEFAULT_SMALL_MODEL = "claude-haiku-3-5"


def get_main_loop_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL") or os.environ.get("CLAUDE_MODEL") or _DEFAULT_MODEL


def get_small_model() -> str:
    return os.environ.get("CLAUDE_SMALL_MODEL") or _DEFAULT_SMALL_MODEL


def is_valid_model(model: str) -> bool:
    return model in KNOWN_MODELS or model.startswith("claude-")


def is_opus_model(model: str) -> bool:
    return "opus" in model.lower()


def is_haiku_model(model: str) -> bool:
    return "haiku" in model.lower()


def model_supports_thinking(model: str) -> bool:
    return is_opus_model(model) or "sonnet-4" in model.lower()


def get_context_window(model: str) -> int:
    if "200k" in model or "opus" in model or "sonnet" in model:
        return 200_000
    if "haiku" in model:
        return 200_000
    return 200_000  # 所有现代 claude 模型

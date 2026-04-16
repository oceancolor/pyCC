# 原始 TS: utils/contextWindow.ts
"""Context 窗口管理（裁剪消息以适应 token 限制）"""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from .tokens import estimate_messages_tokens

MAX_CONTEXT_TOKENS = 200_000
RESERVE_FOR_RESPONSE = 8192


def fit_messages_to_window(
    messages: List[Dict[str, Any]],
    max_tokens: int = MAX_CONTEXT_TOKENS - RESERVE_FOR_RESPONSE,
    keep_system: bool = True,
) -> List[Dict[str, Any]]:
    """裁剪消息列表以适应 token 窗口，从最旧的开始丢弃"""
    if not messages:
        return []

    # 分离 system 消息
    system_msgs = [m for m in messages if m.get("role") == "system"]
    other_msgs = [m for m in messages if m.get("role") != "system"]

    system_tokens = estimate_messages_tokens(system_msgs) if keep_system else 0
    available = max_tokens - system_tokens

    # 从最新到最旧填充
    selected = []
    tokens_used = 0
    for msg in reversed(other_msgs):
        t = estimate_messages_tokens([msg])
        if tokens_used + t <= available:
            selected.insert(0, msg)
            tokens_used += t
        else:
            break

    result = system_msgs + selected if keep_system else selected
    return result


def get_context_usage(messages: List[Dict[str, Any]]) -> float:
    """返回 context 使用率（0.0 ~ 1.0）"""
    tokens = estimate_messages_tokens(messages)
    return min(tokens / MAX_CONTEXT_TOKENS, 1.0)

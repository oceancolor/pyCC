# 原始 TS: utils/tokens.ts
"""Token 计数与估算工具"""
from typing import Any, Dict, Optional


def estimate_token_count(text: str) -> int:
    """粗略估算 token 数（约 4 字符/token）"""
    return max(1, len(text) // 4)


def get_token_count_from_usage(usage: Dict[str, Any]) -> int:
    """从 API usage 对象提取总 token 数"""
    return usage.get("input_tokens", 0) + usage.get("output_tokens", 0)


def estimate_messages_tokens(messages: list) -> int:
    """估算消息列表的总 token 数"""
    total = 0
    for msg in messages:
        content = msg.get("content", "")
        if isinstance(content, str):
            total += estimate_token_count(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    total += estimate_token_count(str(block.get("text", "")))
    return total


def is_context_near_limit(token_count: int, limit: int = 200_000, threshold: float = 0.85) -> bool:
    """判断 context 是否接近上限"""
    return token_count >= limit * threshold

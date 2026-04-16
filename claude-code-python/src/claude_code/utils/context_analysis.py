# 原始 TS: utils/contextAnalysis.ts
"""分析对话 context，判断是否需要压缩、提示等"""
from typing import Any, Dict, List, Tuple

MAX_CONTEXT_TOKENS = 200_000
COMPACT_THRESHOLD = 0.85  # 85% 时触发压缩提示
WARNING_THRESHOLD = 0.70


def analyze_context(messages: List[Dict[str, Any]], current_tokens: int) -> Dict[str, Any]:
    """分析当前 context 状态"""
    ratio = current_tokens / MAX_CONTEXT_TOKENS
    return {
        "token_count": current_tokens,
        "max_tokens": MAX_CONTEXT_TOKENS,
        "usage_ratio": ratio,
        "should_compact": ratio >= COMPACT_THRESHOLD,
        "should_warn": ratio >= WARNING_THRESHOLD,
        "message_count": len(messages),
    }


def get_context_summary(messages: List[Dict[str, Any]]) -> str:
    """生成 context 摘要字符串"""
    user_count = sum(1 for m in messages if m.get("role") == "user")
    asst_count = sum(1 for m in messages if m.get("role") == "assistant")
    return f"{len(messages)} messages ({user_count} user, {asst_count} assistant)"


def find_compaction_boundary(messages: List[Dict[str, Any]], keep_recent: int = 10) -> int:
    """找到可以压缩的边界索引（保留最近 keep_recent 条）"""
    if len(messages) <= keep_recent:
        return 0
    return len(messages) - keep_recent

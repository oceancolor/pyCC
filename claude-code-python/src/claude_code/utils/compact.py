# 原始 TS: utils/compact.ts
"""对话压缩：当 context 过长时截断历史消息"""
from typing import List

MAX_CONTEXT_TOKENS = 100_000
KEEP_RECENT_MESSAGES = 10

# 粗略估算：每个字符约 0.25 token（英文约 4 chars/token，中文约 1.5 chars/token 取中间值）
_CHARS_PER_TOKEN = 4


def estimate_messages_tokens(messages: list) -> int:
    """粗略估算消息列表的 token 数（基于字符数）"""
    total_chars = 0
    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content", "")
        if isinstance(content, str):
            total_chars += len(content)
        elif isinstance(content, list):
            # content 可能是 [{type: "text", text: "..."}, ...]
            for block in content:
                if isinstance(block, dict):
                    total_chars += len(block.get("text", ""))
        total_chars += len(role) + 4  # role + separators overhead
    return total_chars // _CHARS_PER_TOKEN


def should_compact(messages: list, token_count: int) -> bool:
    """判断是否需要压缩：token 超限时返回 True"""
    return token_count >= MAX_CONTEXT_TOKENS


def compact_messages(messages: list, keep_system: bool = True) -> list:
    """保留 system prompt + 最近 N 条消息，丢弃中间历史以节省 context"""
    if not messages:
        return messages

    result: list = []

    if keep_system:
        # 提取所有 system 消息（通常只有开头一条）
        system_msgs = [m for m in messages if m.get("role") == "system"]
        non_system_msgs = [m for m in messages if m.get("role") != "system"]
        result.extend(system_msgs)
    else:
        non_system_msgs = list(messages)

    # 保留最近 KEEP_RECENT_MESSAGES 条非 system 消息
    recent = non_system_msgs[-KEEP_RECENT_MESSAGES:] if non_system_msgs else []
    result.extend(recent)

    return result

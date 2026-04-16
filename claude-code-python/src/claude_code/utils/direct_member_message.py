# 原始 TS: utils/directMemberMessage.ts
"""直接消息发送（团队成员通知）stub"""
from __future__ import annotations
from typing import Optional


async def send_direct_message(
    recipient: str,
    message: str,
    channel: Optional[str] = None,
) -> bool:
    """
    向团队成员发送直接消息（stub）。
    TODO: 接入实际的消息系统（Slack/企微等）
    """
    return False


def format_mention(name: str) -> str:
    return f"@{name}"

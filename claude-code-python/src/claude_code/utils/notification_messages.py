# 原始 TS: utils/notificationMessages.ts
"""通知消息模板"""
from __future__ import annotations
from typing import Optional


def task_complete_message(task: Optional[str] = None) -> str:
    if task:
        return f"✅ 任务完成：{task}"
    return "✅ 任务完成"


def waiting_for_input_message() -> str:
    return "⏳ Claude 正在等待您的输入"


def error_message(error: str) -> str:
    return f"❌ 发生错误：{error}"


def tool_denied_message(tool_name: str, reason: Optional[str] = None) -> str:
    base = f"🚫 工具调用被拒绝：{tool_name}"
    if reason:
        return f"{base}（{reason}）"
    return base


def compact_triggered_message(before: int, after: int) -> str:
    return f"🗜 对话已压缩：{before} → {after} 条消息"


def context_limit_warning(usage_pct: float) -> str:
    return f"⚠️ Context 使用率 {usage_pct:.0%}，建议使用 /compact"

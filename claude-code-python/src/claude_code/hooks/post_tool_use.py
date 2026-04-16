# 原始 TS: utils/hooks.ts (PostToolUse 部分), hooks/useDeferredHookMessages.ts
"""
PostToolUse Hook — 工具调用后的副作用处理。

在工具执行完成后触发，可用于：
  1. 审计日志
  2. 通知外部系统
  3. 触发后续自动化任务

PostToolUse hooks 不能阻断（结果已产生），但可以注入额外消息到对话。

对应 TypeScript 端：
  - PostToolUse event in agentSdkTypes.HOOK_EVENTS
  - useDeferredHookMessages (React hook for async injection)
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .registry import HookRegistry
from .types import (
    AggregatedHookResult,
    HookEvent,
    HookInput,
    HookResultMessage,
)

logger = logging.getLogger(__name__)


async def run_post_tool_use_hooks(
    registry: HookRegistry,
    tool_name: str,
    tool_input: dict[str, Any],
    tool_response: Any,
    session_id: str,
    project_root: Optional[str] = None,
    cwd: Optional[str] = None,
    abort_signal: Optional[Any] = None,
) -> AggregatedHookResult:
    """
    执行 PostToolUse hooks。

    PostToolUse hooks 是纯副作用，结果不影响对话流程。
    任何 DENY 决策在此阶段会被记录但不阻断。

    Returns:
        AggregatedHookResult — 仅供日志/调试使用
    """
    hook_input = HookInput(
        session_id=session_id,
        tool_name=tool_name,
        tool_input=tool_input,
        tool_response=tool_response,
        event_type=HookEvent.POST_TOOL_USE.value,
        project_root=project_root,
        cwd=cwd,
    )

    result = await registry.trigger(
        HookEvent.POST_TOOL_USE,
        hook_input,
        abort_signal=abort_signal,
    )

    logger.debug(
        "PostToolUse hooks done: tool=%s output_texts=%d",
        tool_name,
        len(result.output_texts),
    )
    return result


def extract_hook_result_messages(
    result: AggregatedHookResult,
) -> list[HookResultMessage]:
    """
    将 hook 输出文本转换为可注入对话历史的消息列表。

    对应 TS 端 useDeferredHookMessages 的消息注入逻辑。
    """
    messages: list[HookResultMessage] = []
    for text in result.output_texts:
        if text.strip():
            messages.append(
                HookResultMessage(
                    role="user",
                    content=text,
                    source="hook",
                )
            )
    return messages


def build_post_tool_use_env(
    tool_name: str,
    tool_input: dict[str, Any],
    tool_response: Any,
    session_id: str,
) -> dict[str, str]:
    """
    构建传递给 shell hook 的环境变量（包含工具响应）。
    """
    import json

    response_str = (
        json.dumps(tool_response)
        if not isinstance(tool_response, str)
        else tool_response
    )
    return {
        "HOOK_EVENT_NAME": HookEvent.POST_TOOL_USE.value,
        "TOOL_NAME": tool_name,
        "TOOL_INPUT_JSON": json.dumps(tool_input),
        "TOOL_RESPONSE": response_str[:4096],  # 截断防止环境变量过长
        "SESSION_ID": session_id,
    }

# 原始 TS: hooks/useCanUseTool.tsx, utils/hooks.ts (PreToolUse 部分)
"""
PreToolUse Hook — 工具调用前的权限检查。

在 agent 准备调用某个工具前触发，可以：
  1. 允许继续（ALLOW）
  2. 阻断工具调用（DENY）并向模型返回拒绝消息
  3. 修改工具输入（updated_input）

对应 TypeScript 端：
  - executePermissionRequestHooks() in utils/hooks.ts
  - PreToolUse event in agentSdkTypes.HOOK_EVENTS
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from .registry import HookRegistry
from .types import (
    AggregatedHookResult,
    HookDecision,
    HookEvent,
    HookInput,
)

logger = logging.getLogger(__name__)

# 工具被拒绝时返回给模型的消息模板
REJECT_MESSAGE = "Tool use was rejected by a hook."
REJECT_MESSAGE_WITH_REASON_PREFIX = "Tool use was rejected: "


async def run_pre_tool_use_hooks(
    registry: HookRegistry,
    tool_name: str,
    tool_input: dict[str, Any],
    session_id: str,
    project_root: Optional[str] = None,
    cwd: Optional[str] = None,
    abort_signal: Optional[Any] = None,
) -> tuple[AggregatedHookResult, Optional[str]]:
    """
    执行 PreToolUse hooks，返回聚合结果和拒绝消息。

    Returns:
        (result, reject_message)
        - result.decision == ALLOW: 工具调用放行
        - result.decision == DENY:  工具调用被阻断，reject_message 不为 None
        - result.decision == SKIP:  hook 跳过，视同 ALLOW
    """
    hook_input = HookInput(
        session_id=session_id,
        tool_name=tool_name,
        tool_input=tool_input,
        event_type=HookEvent.PRE_TOOL_USE.value,
        project_root=project_root,
        cwd=cwd,
    )

    result = await registry.trigger(
        HookEvent.PRE_TOOL_USE,
        hook_input,
        abort_signal=abort_signal,
    )

    reject_message: Optional[str] = None
    if result.decision == HookDecision.DENY:
        if result.reason:
            reject_message = f"{REJECT_MESSAGE_WITH_REASON_PREFIX}{result.reason}"
        else:
            reject_message = REJECT_MESSAGE

    logger.debug(
        "PreToolUse hooks done: tool=%s decision=%s",
        tool_name,
        result.decision.value,
    )
    return result, reject_message


def build_pre_tool_use_env(
    tool_name: str,
    tool_input: dict[str, Any],
    session_id: str,
) -> dict[str, str]:
    """
    构建传递给 shell hook 的环境变量。

    对应 TS 端 subprocessEnv() + hook input injection。
    """
    import json

    return {
        "HOOK_EVENT_NAME": HookEvent.PRE_TOOL_USE.value,
        "TOOL_NAME": tool_name,
        "TOOL_INPUT_JSON": json.dumps(tool_input),
        "SESSION_ID": session_id,
    }

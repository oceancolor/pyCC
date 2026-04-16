# 原始 TS: types/hooks.ts, utils/hooks/sessionHooks.ts, utils/hooks/postSamplingHooks.ts
"""
Hook 类型定义。

Claude Code 的 Hooks 系统允许用户在 agent 生命周期的各个关键节点
注册 shell 命令或 Python 函数，以实现权限控制、审计、通知等功能。

支持的 Hook 事件（HookEvent）：
  - PreToolUse    — 工具调用前（可阻断）
  - PostToolUse   — 工具调用后
  - Notification  — 通知/提醒
  - Stop          — agent 停止/完成时
  - SessionStart  — 会话开始时（延迟注入）
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional, Union


# ---------------------------------------------------------------------------
# Hook 事件枚举
# ---------------------------------------------------------------------------

class HookEvent(str, enum.Enum):
    """Hook 触发事件类型，对应 agentSdkTypes.HOOK_EVENTS。"""
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    NOTIFICATION = "Notification"
    STOP = "Stop"
    SESSION_START = "SessionStart"


# 所有合法事件名称（用于验证）
HOOK_EVENTS: list[str] = [e.value for e in HookEvent]


def is_hook_event(value: str) -> bool:
    """判断字符串是否为合法 HookEvent。"""
    return value in HOOK_EVENTS


# ---------------------------------------------------------------------------
# Hook 输入 / 输出
# ---------------------------------------------------------------------------

@dataclass
class HookInput:
    """传递给 hook 的上下文输入。"""
    session_id: str
    tool_name: Optional[str] = None
    tool_input: Optional[dict[str, Any]] = None
    tool_response: Optional[Any] = None        # PostToolUse 专用
    event_type: Optional[str] = None
    project_root: Optional[str] = None
    cwd: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncHookJSONOutput:
    """同步 Hook 的 JSON 输出格式（直接返回结果）。"""
    # 是否继续执行；False 表示阻断当前操作
    continue_: bool = True
    # 可选的原因说明（deny 时填写）
    reason: Optional[str] = None
    # 要注入到会话的额外消息
    output_text: Optional[str] = None
    # 是否静默（不显示 spinner）
    suppress_output: bool = False


@dataclass
class AsyncHookJSONOutput:
    """异步 Hook 的 JSON 输出格式（带 async 标志）。"""
    async_: bool = True
    job_id: Optional[str] = None


# JSON 输出的联合类型
HookJSONOutput = Union[SyncHookJSONOutput, AsyncHookJSONOutput]


# ---------------------------------------------------------------------------
# Hook 决策
# ---------------------------------------------------------------------------

class HookDecision(str, enum.Enum):
    """Hook 对当前操作的最终决策。"""
    ALLOW = "allow"       # 放行
    DENY = "deny"         # 阻断
    SKIP = "skip"         # 跳过（hook 未匹配或超时）


@dataclass
class HookResult:
    """单个 Hook 执行结果。"""
    decision: HookDecision
    reason: Optional[str] = None
    output_text: Optional[str] = None
    exit_code: int = 0
    hook_id: Optional[str] = None


@dataclass
class AggregatedHookResult:
    """多个同类型 Hook 的聚合结果（取最严格的决策）。"""
    decision: HookDecision
    reason: Optional[str] = None
    output_texts: list[str] = field(default_factory=list)
    results: list[HookResult] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Hook 命令定义
# ---------------------------------------------------------------------------

@dataclass
class CommandHook:
    """Shell 命令型 Hook 配置（对应 settings.json 中的配置项）。"""
    type: str = "command"
    command: str = ""
    # 条件过滤（权限规则语法，如 "Bash(git *)"）
    if_condition: Optional[str] = None
    shell: str = "bash"
    timeout: Optional[int] = None        # 秒
    status_message: Optional[str] = None


# 函数 hook 回调签名：接收消息列表，返回 bool（True=通过, False=阻断）
FunctionHookCallback = Callable[
    [list[Any], Optional[Any]],   # (messages, abort_signal)
    Union[bool, Awaitable[bool]]
]


@dataclass
class FunctionHook:
    """Python 函数型 Hook（仅运行时注册，不持久化到配置）。"""
    type: str = "function"
    id: Optional[str] = None
    timeout: Optional[int] = None
    callback: Optional[FunctionHookCallback] = None
    error_message: str = "Hook check failed"
    status_message: Optional[str] = None


# Hook 命令联合类型（支持命令或函数两种形式）
HookCommand = Union[CommandHook, FunctionHook]


# ---------------------------------------------------------------------------
# Session 级别 Hook 状态
# ---------------------------------------------------------------------------

@dataclass
class SessionHookEntry:
    """单条 session hook 注册项（matcher + hook 配置）。"""
    hook: HookCommand
    on_hook_success: Optional[Callable[[HookCommand, AggregatedHookResult], None]] = None


@dataclass
class SessionHookMatcher:
    """按 matcher 分组的 session hooks。"""
    matcher: str
    skill_root: Optional[str] = None
    hooks: list[SessionHookEntry] = field(default_factory=list)


@dataclass
class SessionHooksState:
    """整个 session 中所有事件的 hook 注册状态。"""
    hooks: dict[str, list[SessionHookMatcher]] = field(default_factory=dict)
    # key = HookEvent.value


# ---------------------------------------------------------------------------
# PostSampling Hook（内部 API，不暴露到 settings）
# ---------------------------------------------------------------------------

@dataclass
class REPLHookContext:
    """传递给 PostSampling / Stop hook 的 REPL 上下文。"""
    messages: list[Any]
    system_prompt: Any
    user_context: dict[str, str]
    system_context: dict[str, str]
    tool_use_context: Any
    query_source: Optional[str] = None


PostSamplingHook = Callable[[REPLHookContext], Union[None, Awaitable[None]]]


# ---------------------------------------------------------------------------
# Hook 结果消息（用于 SessionStart 延迟注入）
# ---------------------------------------------------------------------------

@dataclass
class HookResultMessage:
    """Hook 执行后注入到消息历史的消息体。"""
    role: str = "user"
    content: str = ""
    source: str = "hook"

# 原始 TS: utils/hooks/postSamplingHooks.ts, utils/hooks/sessionHooks.ts
"""
Hook 注册表 — 管理 Hook 的注册、触发和注销。

设计原则：
  - HookRegistry 是 session 级单例，非全局单例
  - 支持按 HookEvent 分类注册
  - 触发时按注册顺序执行，取最严格决策（任一 DENY → 整体 DENY）
  - 线程安全（通过 asyncio.Lock 保护并发触发）
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional, Union

from .types import (
    AggregatedHookResult,
    CommandHook,
    FunctionHook,
    FunctionHookCallback,
    HookCommand,
    HookDecision,
    HookEvent,
    HookInput,
    HookResult,
    HookResultMessage,
    PostSamplingHook,
    REPLHookContext,
    SessionHookEntry,
    SessionHookMatcher,
    SessionHooksState,
)

logger = logging.getLogger(__name__)


class HookRegistry:
    """
    Hook 注册表。

    用法示例：
        registry = HookRegistry()
        registry.register(HookEvent.PRE_TOOL_USE, CommandHook(command="echo $TOOL_NAME"))
        result = await registry.trigger(HookEvent.PRE_TOOL_USE, hook_input)
    """

    def __init__(self) -> None:
        # event_type -> list of (matcher, [entries])
        self._state: SessionHooksState = SessionHooksState()
        self._post_sampling_hooks: list[PostSamplingHook] = []
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # 注册 / 注销
    # ------------------------------------------------------------------

    def register(
        self,
        event: Union[HookEvent, str],
        hook: HookCommand,
        matcher: str = "*",
        skill_root: Optional[str] = None,
        on_success=None,
    ) -> None:
        """
        注册一个 hook。

        Args:
            event:      HookEvent 枚举或字符串（如 "PreToolUse"）
            hook:       CommandHook 或 FunctionHook
            matcher:    工具匹配模式（如 "Bash(git *)"，"*" 表示全匹配）
            skill_root: 来源 skill 根目录（可选）
            on_success: 成功回调 (hook, result) -> None
        """
        event_key = event.value if isinstance(event, HookEvent) else event
        entry = SessionHookEntry(hook=hook, on_hook_success=on_success)

        matchers = self._state.hooks.setdefault(event_key, [])
        # 找到已有 matcher 或创建新的
        for m in matchers:
            if m.matcher == matcher and m.skill_root == skill_root:
                m.hooks.append(entry)
                return
        matchers.append(
            SessionHookMatcher(
                matcher=matcher,
                skill_root=skill_root,
                hooks=[entry],
            )
        )
        logger.debug("Hook registered: event=%s matcher=%s", event_key, matcher)

    def unregister(
        self,
        event: Union[HookEvent, str],
        hook_id: str,
    ) -> bool:
        """
        按 FunctionHook.id 注销一个 hook。

        Returns:
            True 表示成功找到并移除，False 表示未找到。
        """
        event_key = event.value if isinstance(event, HookEvent) else event
        matchers = self._state.hooks.get(event_key, [])
        removed = False
        for m in matchers:
            before = len(m.hooks)
            m.hooks = [
                e for e in m.hooks
                if not (
                    isinstance(e.hook, FunctionHook) and e.hook.id == hook_id
                )
            ]
            if len(m.hooks) < before:
                removed = True
        return removed

    def clear(self, event: Optional[Union[HookEvent, str]] = None) -> None:
        """清空指定事件（或所有事件）的 hooks。"""
        if event is None:
            self._state.hooks.clear()
        else:
            event_key = event.value if isinstance(event, HookEvent) else event
            self._state.hooks.pop(event_key, None)

    def register_post_sampling(self, hook: PostSamplingHook) -> None:
        """注册 PostSampling hook（内部 API）。"""
        self._post_sampling_hooks.append(hook)

    def clear_post_sampling(self) -> None:
        """清空所有 PostSampling hooks（用于测试）。"""
        self._post_sampling_hooks.clear()

    # ------------------------------------------------------------------
    # 触发
    # ------------------------------------------------------------------

    async def trigger(
        self,
        event: Union[HookEvent, str],
        hook_input: HookInput,
        abort_signal: Optional[Any] = None,
    ) -> AggregatedHookResult:
        """
        触发指定事件下所有匹配的 hooks，返回聚合结果。

        触发逻辑：
          1. 按 matcher 过滤（简单前缀/全局匹配）
          2. 按注册顺序执行每个 hook
          3. 任一 DENY → 聚合结果为 DENY（短路）
          4. 全部 ALLOW/SKIP → 聚合结果为 ALLOW
        """
        event_key = event.value if isinstance(event, HookEvent) else event
        matchers = self._state.hooks.get(event_key, [])

        results: list[HookResult] = []
        overall_decision = HookDecision.ALLOW
        deny_reason: Optional[str] = None
        output_texts: list[str] = []

        for matcher_group in matchers:
            if not self._matches(matcher_group.matcher, hook_input):
                continue
            for entry in matcher_group.hooks:
                try:
                    result = await self._execute_hook(entry.hook, hook_input, abort_signal)
                    results.append(result)
                    if result.output_text:
                        output_texts.append(result.output_text)
                    if result.decision == HookDecision.DENY:
                        overall_decision = HookDecision.DENY
                        deny_reason = result.reason
                        # 短路：任一 deny 即停止
                        agg = AggregatedHookResult(
                            decision=overall_decision,
                            reason=deny_reason,
                            output_texts=output_texts,
                            results=results,
                        )
                        if entry.on_hook_success:
                            entry.on_hook_success(entry.hook, agg)
                        return agg
                    if entry.on_hook_success:
                        entry.on_hook_success(
                            entry.hook,
                            AggregatedHookResult(
                                decision=result.decision,
                                results=[result],
                            ),
                        )
                except Exception as exc:
                    logger.warning("Hook execution error: %s", exc, exc_info=True)
                    results.append(
                        HookResult(
                            decision=HookDecision.SKIP,
                            reason=str(exc),
                        )
                    )

        return AggregatedHookResult(
            decision=overall_decision,
            reason=deny_reason,
            output_texts=output_texts,
            results=results,
        )

    async def trigger_post_sampling(self, context: REPLHookContext) -> None:
        """触发所有 PostSampling hooks（不影响决策，仅副作用）。"""
        for hook in self._post_sampling_hooks:
            try:
                result = hook(context)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.warning("PostSampling hook error: %s", exc, exc_info=True)

    # ------------------------------------------------------------------
    # 内部执行逻辑
    # ------------------------------------------------------------------

    async def _execute_hook(
        self,
        hook: HookCommand,
        hook_input: HookInput,
        abort_signal: Optional[Any] = None,
    ) -> HookResult:
        """分发到具体 hook 执行器。"""
        if isinstance(hook, FunctionHook):
            return await self._execute_function_hook(hook, hook_input, abort_signal)
        elif isinstance(hook, CommandHook):
            return await self._execute_command_hook(hook, hook_input)
        else:
            logger.warning("Unknown hook type: %s", type(hook))
            return HookResult(decision=HookDecision.SKIP)

    async def _execute_function_hook(
        self,
        hook: FunctionHook,
        hook_input: HookInput,
        abort_signal: Optional[Any] = None,
    ) -> HookResult:
        """执行 Python 函数型 hook。"""
        if hook.callback is None:
            return HookResult(decision=HookDecision.SKIP, reason="no callback")
        try:
            timeout = hook.timeout or 30
            result = hook.callback([], abort_signal)
            if asyncio.iscoroutine(result):
                passed = await asyncio.wait_for(result, timeout=timeout)
            else:
                passed = result
            return HookResult(
                decision=HookDecision.ALLOW if passed else HookDecision.DENY,
                reason=None if passed else hook.error_message,
                hook_id=hook.id,
            )
        except asyncio.TimeoutError:
            return HookResult(
                decision=HookDecision.SKIP,
                reason="timeout",
                hook_id=hook.id,
            )
        except Exception as exc:
            return HookResult(
                decision=HookDecision.SKIP,
                reason=str(exc),
                hook_id=hook.id,
            )

    async def _execute_command_hook(
        self,
        hook: CommandHook,
        hook_input: HookInput,
    ) -> HookResult:
        """
        执行 Shell 命令型 hook。

        环境变量注入：
          TOOL_NAME, TOOL_INPUT_JSON, SESSION_ID, PROJECT_ROOT 等
        """
        # TODO: implement full shell hook execution (env injection, stdout parse, etc.)
        import json
        import os
        import subprocess

        env = os.environ.copy()
        env.update({
            "TOOL_NAME": hook_input.tool_name or "",
            "TOOL_INPUT_JSON": json.dumps(hook_input.tool_input or {}),
            "SESSION_ID": hook_input.session_id,
            "PROJECT_ROOT": hook_input.project_root or "",
            "CWD": hook_input.cwd or "",
        })

        timeout = hook.timeout or 60
        try:
            proc = await asyncio.create_subprocess_shell(
                hook.command,
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            exit_code = proc.returncode or 0
            output = stdout.decode(errors="replace").strip()

            # 约定：exit code 0 = allow，非 0 = deny
            decision = HookDecision.ALLOW if exit_code == 0 else HookDecision.DENY
            reason = stderr.decode(errors="replace").strip() if exit_code != 0 else None

            return HookResult(
                decision=decision,
                reason=reason,
                output_text=output if output else None,
                exit_code=exit_code,
            )
        except asyncio.TimeoutError:
            return HookResult(
                decision=HookDecision.SKIP,
                reason=f"command timed out after {timeout}s",
                exit_code=-1,
            )
        except Exception as exc:
            return HookResult(
                decision=HookDecision.SKIP,
                reason=str(exc),
                exit_code=-1,
            )

    @staticmethod
    def _matches(matcher: str, hook_input: HookInput) -> bool:
        """
        简单 matcher 匹配逻辑。

        支持：
          - "*"           全匹配
          - "ToolName"    精确匹配 tool_name
          - "ToolName(*)" 前缀匹配（TODO: 完整权限规则语法）
        """
        if matcher == "*":
            return True
        if hook_input.tool_name is None:
            return False
        # 简单精确匹配
        if matcher == hook_input.tool_name:
            return True
        # 前缀匹配 "ToolName(*)" 或 "ToolName(pattern)"
        if "(" in matcher:
            prefix = matcher.split("(")[0]
            if prefix == hook_input.tool_name:
                return True
        return False

    # ------------------------------------------------------------------
    # 状态快照
    # ------------------------------------------------------------------

    def get_state(self) -> SessionHooksState:
        """返回当前 hooks 注册状态快照（只读）。"""
        return self._state

    def has_hooks(self, event: Union[HookEvent, str]) -> bool:
        """判断指定事件是否有任何注册的 hooks。"""
        event_key = event.value if isinstance(event, HookEvent) else event
        matchers = self._state.hooks.get(event_key, [])
        return any(len(m.hooks) > 0 for m in matchers)

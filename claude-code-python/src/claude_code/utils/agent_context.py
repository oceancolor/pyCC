# 原始 TS: utils/agentContext.ts
"""Agent 运行时上下文（工具+配置的轻量封装，与 context.py 互补）"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class ToolCallRecord:
    """记录一次工具调用"""
    tool_name: str
    input: Dict[str, Any]
    output: Optional[str] = None
    error: Optional[str] = None
    duration_ms: Optional[float] = None


@dataclass
class AgentRunContext:
    """
    单次 agent 运行的上下文，传递给每个工具调用。
    对应 TS 中传给 tool.call() 的 context 参数。
    """
    session_id: str
    model: str
    cwd: str = ""
    verbose: bool = False
    debug: bool = False
    max_tokens: int = 8192
    tool_call_history: List[ToolCallRecord] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def record_tool_call(self, record: ToolCallRecord) -> None:
        self.tool_call_history.append(record)

    @property
    def last_tool_call(self) -> Optional[ToolCallRecord]:
        return self.tool_call_history[-1] if self.tool_call_history else None

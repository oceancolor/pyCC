# 原始 TS: context.ts
"""全局上下文管理：工具、hooks、session 状态的统一入口"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .state.session_state import SessionState
from .hooks.registry import HookRegistry


@dataclass
class AgentContext:
    """Agent 运行上下文，贯穿整个 agentic 循环"""
    session: SessionState
    hooks: HookRegistry = field(default_factory=HookRegistry)
    tools: List[Any] = field(default_factory=list)
    verbose: bool = False
    debug: bool = False
    max_iterations: int = 10
    extra: Dict[str, Any] = field(default_factory=dict)

    def register_tool(self, tool: Any) -> None:
        self.tools.append(tool)

    def get_tool(self, name: str) -> Optional[Any]:
        for t in self.tools:
            if hasattr(t, "name") and t.name == name:
                return t
        return None

    @property
    def tool_names(self) -> List[str]:
        return [t.name for t in self.tools if hasattr(t, "name")]


# 模块级全局上下文（可选用）
_current_context: Optional[AgentContext] = None

def get_context() -> Optional[AgentContext]:
    return _current_context

def set_context(ctx: AgentContext) -> None:
    global _current_context
    _current_context = ctx

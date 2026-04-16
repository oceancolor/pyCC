# 原始 TS: state/
"""Session 运行时状态"""
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
import time


@dataclass
class SessionState:
    session_id: str
    model: str = "claude-opus-4-5"
    messages: List[Dict[str, Any]] = field(default_factory=list)
    system_prompt: Optional[str] = None
    start_time: float = field(default_factory=time.time)
    input_tokens: int = 0
    output_tokens: int = 0
    iteration: int = 0
    is_active: bool = True
    cwd: str = ""
    title: Optional[str] = None

    def add_message(self, role: str, content: Any) -> None:
        self.messages.append({"role": role, "content": content})

    def update_usage(self, input_tokens: int, output_tokens: int) -> None:
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

# 原始 TS: utils/extraUsage.ts
"""额外 usage 统计（cache tokens、工具调用次数等）"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict


@dataclass
class ExtraUsage:
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0
    tool_call_count: int = 0
    tool_error_count: int = 0
    web_search_count: int = 0
    custom: Dict[str, int] = field(default_factory=dict)

    def merge(self, other: "ExtraUsage") -> None:
        self.cache_read_input_tokens += other.cache_read_input_tokens
        self.cache_creation_input_tokens += other.cache_creation_input_tokens
        self.tool_call_count += other.tool_call_count
        self.tool_error_count += other.tool_error_count
        self.web_search_count += other.web_search_count
        for k, v in other.custom.items():
            self.custom[k] = self.custom.get(k, 0) + v

    def increment(self, key: str, amount: int = 1) -> None:
        self.custom[key] = self.custom.get(key, 0) + amount


_session_extra = ExtraUsage()

def get_extra_usage() -> ExtraUsage:
    return _session_extra

def reset_extra_usage() -> None:
    global _session_extra
    _session_extra = ExtraUsage()

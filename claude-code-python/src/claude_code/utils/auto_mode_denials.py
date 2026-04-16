# 原始 TS: utils/autoModeDenials.ts
"""自动模式拒绝记录（跟踪被权限系统拒绝的操作）"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional
import time


@dataclass
class DenialRecord:
    tool_name: str
    reason: str
    timestamp: float = field(default_factory=time.time)
    input_summary: Optional[str] = None


class AutoModeDenialTracker:
    """记录自动模式下被拒绝的工具调用"""

    def __init__(self) -> None:
        self._denials: List[DenialRecord] = []

    def record(self, tool_name: str, reason: str, input_summary: Optional[str] = None) -> None:
        self._denials.append(DenialRecord(
            tool_name=tool_name,
            reason=reason,
            input_summary=input_summary,
        ))

    def get_recent(self, n: int = 10) -> List[DenialRecord]:
        return self._denials[-n:]

    def count(self) -> int:
        return len(self._denials)

    def clear(self) -> None:
        self._denials.clear()

    def has_denials(self) -> bool:
        return bool(self._denials)

    def summary(self) -> str:
        if not self._denials:
            return "无拒绝记录"
        by_tool: dict = {}
        for d in self._denials:
            by_tool[d.tool_name] = by_tool.get(d.tool_name, 0) + 1
        parts = [f"{tool}×{cnt}" for tool, cnt in by_tool.items()]
        return "拒绝: " + ", ".join(parts)


_tracker = AutoModeDenialTracker()

def get_denial_tracker() -> AutoModeDenialTracker:
    return _tracker

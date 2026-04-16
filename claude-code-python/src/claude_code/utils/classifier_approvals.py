# 原始 TS: utils/classifierApprovals.ts / utils/classifierApprovalsHook.ts
"""工具调用权限分类器（基于规则的自动批准/拒绝）"""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Pattern


class ApprovalDecision(str, Enum):
    APPROVE = "approve"
    DENY = "deny"
    ASK = "ask"


@dataclass
class ApprovalRule:
    tool_name: str
    pattern: Optional[str] = None        # 匹配 input 的正则
    decision: ApprovalDecision = ApprovalDecision.ASK
    reason: str = ""
    _compiled: Optional[Pattern] = field(default=None, repr=False)

    def __post_init__(self):
        if self.pattern:
            self._compiled = re.compile(self.pattern, re.IGNORECASE)

    def matches(self, tool_name: str, input_str: str) -> bool:
        if self.tool_name != "*" and self.tool_name != tool_name:
            return False
        if self._compiled:
            return bool(self._compiled.search(input_str))
        return True


class ClassifierApprovals:
    """基于规则的工具调用审批分类器"""

    def __init__(self) -> None:
        self._rules: List[ApprovalRule] = []
        self._setup_defaults()

    def _setup_defaults(self) -> None:
        # 默认拒绝危险命令
        dangerous = [r"rm\s+-rf\s+/", r"dd\s+if=", r"mkfs", r":(){:|:&};:"]
        for pat in dangerous:
            self._rules.append(ApprovalRule(
                tool_name="Bash", pattern=pat,
                decision=ApprovalDecision.DENY,
                reason="危险命令",
            ))

    def add_rule(self, rule: ApprovalRule) -> None:
        self._rules.insert(0, rule)  # 后添加的优先

    def classify(self, tool_name: str, tool_input: Dict[str, Any]) -> ApprovalDecision:
        input_str = str(tool_input)
        for rule in self._rules:
            if rule.matches(tool_name, input_str):
                return rule.decision
        return ApprovalDecision.ASK

    def is_auto_approved(self, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        return self.classify(tool_name, tool_input) == ApprovalDecision.APPROVE

    def is_denied(self, tool_name: str, tool_input: Dict[str, Any]) -> bool:
        return self.classify(tool_name, tool_input) == ApprovalDecision.DENY


_classifier = ClassifierApprovals()

def get_classifier() -> ClassifierApprovals:
    return _classifier

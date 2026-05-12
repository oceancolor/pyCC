"""
Permission result types.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Union


class PermissionAllowDecision:
    behavior: Literal["allow"] = "allow"
    rule: Optional[Any] = None
    source: Optional[str] = None


class PermissionAskDecision:
    behavior: Literal["ask"] = "ask"
    decision_reason: Optional[str] = None


class PermissionDenyDecision:
    behavior: Literal["deny"] = "deny"
    reason: str = ""


PermissionBehavior = str  # 'allow' | 'deny' | 'ask'
PermissionDecision = Union[PermissionAllowDecision, PermissionAskDecision, PermissionDenyDecision]
PermissionDecisionReason = str
PermissionMetadata = Dict[str, Any]


class PermissionResult:
    def __init__(self, behavior: PermissionBehavior, **kwargs: Any) -> None:
        self.behavior = behavior
        for k, v in kwargs.items():
            setattr(self, k, v)


def get_rule_behavior_description(permission_result_behavior: str) -> str:
    """Get the appropriate prose description for rule behavior."""
    if permission_result_behavior == "allow":
        return "allowed"
    elif permission_result_behavior == "deny":
        return "denied"
    return "asked for confirmation for"

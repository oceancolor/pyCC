"""
Permission rule types and schemas.
"""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional, Union

PermissionBehavior = str  # 'allow' | 'deny' | 'ask'
PermissionRuleSource = str
PermissionRuleValue = Dict[str, Any]


class PermissionRule:
    """A permission rule."""
    def __init__(
        self,
        behavior: PermissionBehavior,
        tool_name: str,
        rule_content: Optional[str] = None,
        source: Optional[PermissionRuleSource] = None,
    ) -> None:
        self.behavior = behavior
        self.tool_name = tool_name
        self.rule_content = rule_content
        self.source = source

    def to_dict(self) -> Dict[str, Any]:
        return {
            "behavior": self.behavior,
            "toolName": self.tool_name,
            "ruleContent": self.rule_content,
            "source": self.source,
        }

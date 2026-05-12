"""
Permission update - handles permission rule CRUD operations.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class PermissionUpdate:
    """Represents a permission rule update operation."""
    def __init__(
        self,
        operation: str,  # 'add' | 'remove'
        behavior: str,   # 'allow' | 'deny' | 'ask'
        tool_name: str,
        rule_content: Optional[str] = None,
        source: Optional[str] = None,
    ) -> None:
        self.operation = operation
        self.behavior = behavior
        self.tool_name = tool_name
        self.rule_content = rule_content
        self.source = source


def apply_permission_update(
    rules: List[Dict[str, Any]],
    update: PermissionUpdate,
) -> List[Dict[str, Any]]:
    """Apply a permission update to a list of rules."""
    if update.operation == "add":
        new_rule = {
            "behavior": update.behavior,
            "toolName": update.tool_name,
            "ruleContent": update.rule_content,
        }
        return [r for r in rules if not _rules_match(r, new_rule)] + [new_rule]
    elif update.operation == "remove":
        return [
            r for r in rules
            if not (
                r.get("toolName") == update.tool_name
                and r.get("behavior") == update.behavior
                and r.get("ruleContent") == update.rule_content
            )
        ]
    return rules


def _rules_match(a: Dict[str, Any], b: Dict[str, Any]) -> bool:
    """Check if two rules have the same identity."""
    return (
        a.get("toolName") == b.get("toolName")
        and a.get("ruleContent") == b.get("ruleContent")
    )

"""
Permission explainer - provides human-readable explanations for permission decisions.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def explain_permission_decision(
    tool_name: str,
    tool_input: Dict[str, Any],
    decision: str,
    rule: Optional[Dict[str, Any]] = None,
    mode: str = "default",
) -> str:
    """
    Provide a human-readable explanation for a permission decision.
    """
    if decision == "allow":
        if rule:
            rule_content = rule.get("ruleContent", "")
            if rule_content:
                return f"Tool {tool_name} was allowed by rule: {rule_content}"
            return f"Tool {tool_name} was allowed"
        if mode == "bypassPermissions":
            return f"Tool {tool_name} was allowed (bypass permissions mode)"
        if mode == "acceptEdits":
            return f"Tool {tool_name} was allowed (accept edits mode)"
        return f"Tool {tool_name} was allowed"
    elif decision == "deny":
        if rule:
            rule_content = rule.get("ruleContent", "")
            if rule_content:
                return f"Tool {tool_name} was denied by rule: {rule_content}"
            return f"Tool {tool_name} was denied"
        return f"Tool {tool_name} was denied"
    else:
        return f"Asking permission to run {tool_name}"


def format_permission_rule(
    tool_name: str,
    behavior: str,
    rule_content: Optional[str] = None,
) -> str:
    """Format a permission rule as a human-readable string."""
    if rule_content:
        return f"{tool_name}({rule_content})"
    return tool_name


def get_permission_explanation(
    tool_name: str,
    behavior: str,
) -> str:
    """Get a brief explanation of what a permission behavior means."""
    if behavior == "allow":
        return f"Always allow {tool_name}"
    elif behavior == "deny":
        return f"Always deny {tool_name}"
    elif behavior == "ask":
        return f"Always ask before running {tool_name}"
    return f"Unknown behavior for {tool_name}"

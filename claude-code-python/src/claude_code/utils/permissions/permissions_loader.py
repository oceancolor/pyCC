"""
Permissions loader - loads and aggregates permission rules from settings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def load_permission_rules(
    sources: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """Load permission rules from settings sources."""
    all_rules: List[Dict[str, Any]] = []

    sources = sources or ["projectSettings", "userSettings", "localSettings", "policySettings"]

    for source in sources:
        try:
            from ..settings.settings import get_settings_for_source
            settings = get_settings_for_source(source)
            if settings is None:
                continue
            rules = settings.get("permissions", []) or []
            for rule in rules:
                if isinstance(rule, dict):
                    all_rules.append({**rule, "source": source})
        except Exception:
            pass

    return all_rules


def find_matching_rule(
    tool_name: str,
    tool_input: Dict[str, Any],
    rules: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Find the first rule matching the given tool name."""
    for rule in rules:
        if rule.get("toolName") == tool_name:
            return rule
    return None


def get_effective_permission(
    tool_name: str,
    tool_input: Dict[str, Any],
    mode: str = "default",
) -> str:
    """
    Get the effective permission for a tool call.
    Returns 'allow', 'deny', or 'ask'.
    """
    if mode == "bypassPermissions":
        return "allow"
    if mode == "dontAsk":
        return "allow"
    if mode == "acceptEdits":
        return "allow"

    rules = load_permission_rules()
    rule = find_matching_rule(tool_name, tool_input, rules)

    if rule:
        return rule.get("behavior", "ask")

    return "ask"

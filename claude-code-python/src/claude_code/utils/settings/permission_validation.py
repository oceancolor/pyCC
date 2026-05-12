"""
Permission validation - validates permission rules in settings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


VALID_BEHAVIORS = ("allow", "deny", "ask")


def validate_permission_rule(rule: Any) -> Tuple[bool, Optional[str]]:
    """Validate a single permission rule. Returns (is_valid, error_message)."""
    if not isinstance(rule, dict):
        return False, "Permission rule must be an object"

    tool_name = rule.get("toolName")
    if not tool_name or not isinstance(tool_name, str):
        return False, "Permission rule must have a 'toolName' string field"

    behavior = rule.get("behavior")
    if behavior not in VALID_BEHAVIORS:
        return False, f"Permission rule 'behavior' must be one of: {', '.join(VALID_BEHAVIORS)}"

    rule_content = rule.get("ruleContent")
    if rule_content is not None and not isinstance(rule_content, str):
        return False, "Permission rule 'ruleContent' must be a string if present"

    return True, None


def validate_permissions_list(permissions: Any) -> List[str]:
    """Validate a list of permission rules. Returns list of error messages."""
    if permissions is None:
        return []
    if not isinstance(permissions, list):
        return ["'permissions' must be an array"]

    errors = []
    for i, rule in enumerate(permissions):
        valid, error = validate_permission_rule(rule)
        if not valid:
            errors.append(f"permissions[{i}]: {error}")
    return errors

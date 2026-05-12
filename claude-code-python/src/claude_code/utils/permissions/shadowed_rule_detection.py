"""
Shadowed rule detection - detects when permission rules are shadowed by others.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple


class ShadowedRuleInfo:
    """Information about a rule that shadows another rule."""
    def __init__(
        self,
        shadowing_rule: Dict[str, Any],
        shadowed_rule: Dict[str, Any],
        reason: str,
    ) -> None:
        self.shadowing_rule = shadowing_rule
        self.shadowed_rule = shadowed_rule
        self.reason = reason


def detect_shadowed_rules(
    rules: List[Dict[str, Any]],
) -> List[ShadowedRuleInfo]:
    """
    Detect rules that are completely shadowed by earlier (higher-priority) rules.
    A rule is shadowed if another rule with the same or broader tool_name and
    rule_content pattern would always match before it.
    """
    shadowed: List[ShadowedRuleInfo] = []

    for i, rule in enumerate(rules):
        for j, earlier_rule in enumerate(rules[:i]):
            if _rule_shadows(earlier_rule, rule):
                shadowed.append(
                    ShadowedRuleInfo(
                        shadowing_rule=earlier_rule,
                        shadowed_rule=rule,
                        reason=f"Rule at index {j} shadows rule at index {i}",
                    )
                )
                break

    return shadowed


def _rule_shadows(earlier: Dict[str, Any], later: Dict[str, Any]) -> bool:
    """Check if 'earlier' rule shadows 'later' rule."""
    # Same tool name and behavior already covers this case
    if earlier.get("toolName") != later.get("toolName"):
        return False

    earlier_content = earlier.get("ruleContent")
    later_content = later.get("ruleContent")

    # If earlier rule has no ruleContent (matches everything for this tool),
    # it shadows any more-specific later rule.
    if earlier_content is None and later_content is not None:
        return True

    # If both have the same rule content, same behavior means shadowed.
    if earlier_content == later_content:
        return earlier.get("behavior") == later.get("behavior")

    return False


def get_shadowed_rule_warning(info: ShadowedRuleInfo) -> str:
    """Get a human-readable warning for a shadowed rule."""
    shadowing = info.shadowing_rule
    shadowed = info.shadowed_rule
    return (
        f"Rule '{_format_rule(shadowed)}' is shadowed by '{_format_rule(shadowing)}'"
        f" and will never be applied."
    )


def _format_rule(rule: Dict[str, Any]) -> str:
    tool_name = rule.get("toolName", "unknown")
    rule_content = rule.get("ruleContent", "")
    behavior = rule.get("behavior", "unknown")
    if rule_content:
        return f"{behavior}:{tool_name}({rule_content})"
    return f"{behavior}:{tool_name}"

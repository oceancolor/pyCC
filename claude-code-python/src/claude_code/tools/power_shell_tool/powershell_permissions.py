"""
powershell_permissions.py — PowerShell permission checking.
Ported from PowerShellTool/powershellPermissions.ts (1648 lines).

Python port of the PowerShell-specific permission rule matching and
tool-permission-check logic, adapted from bashPermissions.ts for
case-insensitive cmdlet matching.
"""
from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class PermissionResult:
    allowed: bool
    message: str = ""
    decision_reason: str = ""


@dataclass
class ShellPermissionRule:
    """Parsed permission rule for a shell/PowerShell command."""
    rule: str
    is_exact: bool = False
    is_prefix: bool = False
    is_wildcard: bool = False
    pattern: str = ""


@dataclass
class PermissionUpdate:
    """A suggested permission rule update."""
    rule: str
    description: str = ""


# ---------------------------------------------------------------------------
# Git safety sets
# ---------------------------------------------------------------------------

GIT_SAFETY_WRITE_CMDLETS = frozenset([
    'new-item', 'set-content', 'add-content', 'out-file',
    'copy-item', 'move-item', 'rename-item', 'expand-archive',
    'invoke-webrequest', 'invoke-restmethod', 'tee-object',
    'export-csv', 'export-clixml',
])

GIT_SAFETY_ARCHIVE_EXTRACTORS = frozenset([
    'tar', 'tar.exe', 'bsdtar', 'bsdtar.exe',
    'unzip', 'unzip.exe', '7z', '7z.exe',
    '7za', '7za.exe', 'gzip', 'gzip.exe',
    'gunzip', 'gunzip.exe', 'expand-archive',
])

PS_ASSIGN_PREFIX_RE = re.compile(r'^\$[\w:]+\s*(?:[+\-*/%]|\?\?)?\s*=\s*')


# ---------------------------------------------------------------------------
# Rule parsing helpers (shared with bash permissions)
# ---------------------------------------------------------------------------

def _has_wildcards(rule: str) -> bool:
    return '*' in rule or '?' in rule


def parse_permission_rule(rule: str) -> ShellPermissionRule:
    """Parse a permission rule string into a structured rule object."""
    if rule.endswith('*'):
        return ShellPermissionRule(
            rule=rule,
            is_prefix=True,
            pattern=rule[:-1].lower(),
        )
    if _has_wildcards(rule):
        return ShellPermissionRule(
            rule=rule,
            is_wildcard=True,
            pattern=rule.lower(),
        )
    return ShellPermissionRule(
        rule=rule,
        is_exact=True,
        pattern=rule.lower(),
    )


def powershell_permission_rule(permission_rule: str) -> ShellPermissionRule:
    """Parse a PowerShell permission rule."""
    return parse_permission_rule(permission_rule)


def match_wildcard_pattern(pattern: str, command: str) -> bool:
    """Match a command against a wildcard pattern (case-insensitive)."""
    p = re.escape(pattern.lower()).replace(r'\*', '.*').replace(r'\?', '.')
    return bool(re.fullmatch(p, command.lower()))


def _matches_rule(rule: ShellPermissionRule, command: str) -> bool:
    """Check if a command matches a permission rule."""
    cmd_lower = command.lower()
    if rule.is_exact:
        return cmd_lower == rule.pattern
    if rule.is_prefix:
        return cmd_lower.startswith(rule.pattern)
    if rule.is_wildcard:
        return match_wildcard_pattern(rule.pattern, command)
    return False


# ---------------------------------------------------------------------------
# Suggestion helpers
# ---------------------------------------------------------------------------

def _suggestion_for_exact_command(command: str) -> List[PermissionUpdate]:
    """Generate exact-match permission suggestion for a command."""
    if '\n' in command or '*' in command:
        return []
    return [PermissionUpdate(rule=command, description=f"Allow exact: {command}")]


def _suggestion_for_prefix(prefix: str) -> List[PermissionUpdate]:
    """Generate prefix-match permission suggestion."""
    return [PermissionUpdate(rule=f"{prefix}*", description=f"Allow prefix: {prefix}*")]


def _get_suggestions(command: str) -> List[PermissionUpdate]:
    """Get permission update suggestions for a command."""
    suggestions = []
    # Exact match suggestion
    suggestions.extend(_suggestion_for_exact_command(command))
    # Prefix suggestion (first word)
    first_word = command.split()[0] if command.split() else command
    if first_word != command:
        suggestions.extend(_suggestion_for_prefix(first_word + " "))
    return suggestions


# ---------------------------------------------------------------------------
# Core permission check functions
# ---------------------------------------------------------------------------

def powershell_tool_check_exact_match_permission(
    command: str,
    rules: List[str],
) -> Optional[PermissionResult]:
    """
    Check if a PowerShell command exactly matches any permission rule.
    Returns PermissionResult if matched, None if no match.
    """
    parsed_rules = [parse_permission_rule(r) for r in rules]
    cmd_lower = command.lower().strip()

    for rule in parsed_rules:
        if _matches_rule(rule, cmd_lower):
            return PermissionResult(
                allowed=True,
                message="",
                decision_reason=f"Matched rule: {rule.rule}",
            )
    return None


def powershell_tool_check_permission(
    command: str,
    rules: List[str],
    cwd: Optional[str] = None,
    permission_mode: str = "default",
) -> PermissionResult:
    """
    Full permission check for a PowerShell command against a set of rules.
    Returns PermissionResult with allowed=True if permitted.
    """
    if not command.strip():
        return PermissionResult(allowed=False, message="Empty command")

    # Check exact/prefix/wildcard rules
    exact = powershell_tool_check_exact_match_permission(command, rules)
    if exact is not None:
        return exact

    # YOLO mode — allow everything
    if permission_mode in ("acceptEdits", "bypassPermissions", "yolo"):
        return PermissionResult(
            allowed=True,
            message="",
            decision_reason="YOLO/bypass mode",
        )

    # No matching rule found — require user approval
    suggestions = _get_suggestions(command)
    suggestion_text = ""
    if suggestions:
        suggestion_text = " Suggested rules: " + ", ".join(f"`{s.rule}`" for s in suggestions)

    return PermissionResult(
        allowed=False,
        message=f"No permission rule matches: `{command}`.{suggestion_text}",
        decision_reason="no_matching_rule",
    )


async def powershell_tool_has_permission(
    command: str,
    context: Any = None,
    permission_context: Any = None,
) -> PermissionResult:
    """
    Async version: full permission gate for PowerShell tool execution.
    Checks security constraints, git safety, and permission rules.
    """
    if not command or not command.strip():
        return PermissionResult(allowed=False, message="Empty command")

    # Bypass permission check modes
    permission_mode = "default"
    if permission_context:
        permission_mode = getattr(permission_context, "permission_mode", "default")

    if permission_mode in ("acceptEdits", "bypassPermissions"):
        return PermissionResult(allowed=True)

    # Security check
    try:
        from claude_code.tools.power_shell_tool.powershell_security import (
            powershell_command_is_safe,
        )
        sec_result = powershell_command_is_safe(command)
        if not sec_result.get("allowed", True):
            return PermissionResult(
                allowed=False,
                message=sec_result.get("message", "Security check failed"),
                decision_reason="security_check",
            )
    except ImportError:
        pass

    # Permission rules check
    rules: List[str] = []
    if permission_context:
        rules = getattr(permission_context, "powershell_rules", []) or []

    return powershell_tool_check_permission(
        command, rules,
        cwd=os.getcwd(),
        permission_mode=permission_mode,
    )


# ---------------------------------------------------------------------------
# Public aliases matching TS exports
# ---------------------------------------------------------------------------

def get_suggestions_for_command(command: str) -> List[PermissionUpdate]:
    """Get permission update suggestions for a PowerShell command."""
    return _get_suggestions(command)

"""
Shell rule matching - matches shell commands against permission rules.
"""

from __future__ import annotations

import re
import shlex
from typing import Any, Dict, List, Optional, Tuple


def normalize_command(command: str) -> str:
    """Normalize a command string for matching."""
    return command.strip()


def match_shell_rule(
    rule_content: str,
    command: str,
) -> bool:
    """
    Check if a shell command matches a permission rule content.
    Rule content can be:
    - Exact command string (must start with)
    - Prefix with wildcards (e.g., 'git *')
    - Regex pattern (prefixed with 'regex:')
    """
    if not rule_content:
        return True  # Empty rule content matches everything

    cmd = normalize_command(command)
    rule = normalize_command(rule_content)

    # Handle regex patterns
    if rule.startswith("regex:"):
        pattern = rule[6:]
        try:
            return bool(re.search(pattern, cmd))
        except re.error:
            return False

    # Handle wildcard glob-style patterns
    if "*" in rule:
        # Convert glob pattern to regex
        escaped = re.escape(rule)
        regex = escaped.replace(r"\*", ".*")
        try:
            return bool(re.match(f"^{regex}$", cmd))
        except re.error:
            return False

    # Simple prefix match
    return cmd == rule or cmd.startswith(rule + " ") or cmd.startswith(rule + "\t")


def find_matching_shell_rule(
    command: str,
    rules: List[Dict[str, Any]],
    tool_name: str = "Bash",
) -> Optional[Dict[str, Any]]:
    """
    Find the first rule that matches the given shell command.
    Returns the matching rule or None.
    """
    for rule in rules:
        if rule.get("toolName") != tool_name:
            continue
        rule_content = rule.get("ruleContent", "")
        if match_shell_rule(rule_content, command):
            return rule
    return None


def extract_base_command(command: str) -> str:
    """Extract the base command name from a shell command string."""
    try:
        parts = shlex.split(command)
        return parts[0] if parts else ""
    except ValueError:
        # Malformed command
        words = command.split()
        return words[0] if words else ""


def command_matches_prefix(command: str, prefix: str) -> bool:
    """Check if a command starts with the given prefix (word-boundary aware)."""
    cmd = normalize_command(command)
    pre = normalize_command(prefix)
    if not pre:
        return True
    if cmd == pre:
        return True
    return cmd.startswith(pre + " ") or cmd.startswith(pre + "\t")

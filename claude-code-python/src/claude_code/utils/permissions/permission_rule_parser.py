"""
Permission rule parser utilities.
Ported from utils/permissions/permissionRuleParser.ts

Parses and serializes permission rule strings of the form:
  "ToolName" or "ToolName(content)"
"""
from __future__ import annotations

import os
from typing import Dict, Optional, TypedDict


# ---------------------------------------------------------------------------
# Feature flags (mirrors bun:bundle's feature())
# ---------------------------------------------------------------------------

def _feature(name: str) -> bool:
    return os.environ.get(f"FEATURE_{name}", "").lower() in ("1", "true", "yes")


# ---------------------------------------------------------------------------
# Tool name constants (imported lazily to avoid circular imports)
# ---------------------------------------------------------------------------

def _get_agent_tool_name() -> str:
    try:
        from claude_code.tools.agent_tool.constants import AGENT_TOOL_NAME  # type: ignore
        return AGENT_TOOL_NAME
    except ImportError:
        return "Agent"


def _get_task_output_tool_name() -> str:
    try:
        from claude_code.tools.task_output_tool.constants import TASK_OUTPUT_TOOL_NAME  # type: ignore
        return TASK_OUTPUT_TOOL_NAME
    except ImportError:
        return "TaskOutput"


def _get_task_stop_tool_name() -> str:
    try:
        from claude_code.tools.task_stop_tool.prompt import TASK_STOP_TOOL_NAME  # type: ignore
        return TASK_STOP_TOOL_NAME
    except ImportError:
        return "TaskStop"


def _get_brief_tool_name() -> Optional[str]:
    if not (_feature("KAIROS") or _feature("KAIROS_BRIEF")):
        return None
    try:
        from claude_code.tools.brief_tool.prompt import BRIEF_TOOL_NAME  # type: ignore
        return BRIEF_TOOL_NAME
    except ImportError:
        return None


def _build_legacy_aliases() -> Dict[str, str]:
    aliases: Dict[str, str] = {
        "Task": _get_agent_tool_name(),
        "KillShell": _get_task_stop_tool_name(),
        "AgentOutputTool": _get_task_output_tool_name(),
        "BashOutputTool": _get_task_output_tool_name(),
    }
    brief = _get_brief_tool_name()
    if brief:
        aliases["Brief"] = brief
    return aliases


# Lazily built on first use
_LEGACY_TOOL_NAME_ALIASES: Optional[Dict[str, str]] = None


def _get_aliases() -> Dict[str, str]:
    global _LEGACY_TOOL_NAME_ALIASES
    if _LEGACY_TOOL_NAME_ALIASES is None:
        _LEGACY_TOOL_NAME_ALIASES = _build_legacy_aliases()
    return _LEGACY_TOOL_NAME_ALIASES


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class PermissionRuleValue(TypedDict, total=False):
    toolName: str
    ruleContent: Optional[str]


def normalize_legacy_tool_name(name: str) -> str:
    """Return the canonical tool name, resolving legacy aliases."""
    return _get_aliases().get(name, name)


def get_legacy_tool_names(canonical_name: str) -> list:
    """Return all legacy names that map to *canonical_name*."""
    return [k for k, v in _get_aliases().items() if v == canonical_name]


def escape_rule_content(content: str) -> str:
    r"""Escape special characters in rule content for safe storage.

    Escaping order:
    1. Backslashes (``\`` → ``\\``)
    2. Parentheses (``(`` → ``\(``, ``)`` → ``\)``)

    >>> escape_rule_content('psycopg2.connect()')
    'psycopg2.connect\\(\\)'
    """
    return content.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def unescape_rule_content(content: str) -> str:
    r"""Reverse the escaping done by :func:`escape_rule_content`.

    Unescaping order (reverse of escaping):
    1. Parentheses (``\(`` → ``(``, ``\)`` → ``)``)
    2. Backslashes (``\\`` → ``\``)

    >>> unescape_rule_content('psycopg2.connect\\(\\)')
    'psycopg2.connect()'
    """
    content = content.replace("\\(", "(").replace("\\)", ")")
    content = content.replace("\\\\", "\\")
    return content


def _find_first_unescaped(s: str, char: str) -> int:
    """Return the index of the first unescaped *char* in *s*, or -1."""
    for i, c in enumerate(s):
        if c == char:
            # Count preceding backslashes
            backslash_count = 0
            j = i - 1
            while j >= 0 and s[j] == "\\":
                backslash_count += 1
                j -= 1
            if backslash_count % 2 == 0:
                return i
    return -1


def _find_last_unescaped(s: str, char: str) -> int:
    """Return the index of the last unescaped *char* in *s*, or -1."""
    for i in range(len(s) - 1, -1, -1):
        if s[i] == char:
            backslash_count = 0
            j = i - 1
            while j >= 0 and s[j] == "\\":
                backslash_count += 1
                j -= 1
            if backslash_count % 2 == 0:
                return i
    return -1


def permission_rule_value_from_string(rule_string: str) -> PermissionRuleValue:
    """Parse a permission rule string into its components.

    Format: ``"ToolName"`` or ``"ToolName(content)"``.
    Content may contain escaped parentheses: ``\\(`` and ``\\)``.

    >>> permission_rule_value_from_string('Bash')
    {'toolName': 'Bash'}
    >>> permission_rule_value_from_string('Bash(npm install)')
    {'toolName': 'Bash', 'ruleContent': 'npm install'}
    """
    open_idx = _find_first_unescaped(rule_string, "(")
    if open_idx == -1:
        return {"toolName": normalize_legacy_tool_name(rule_string)}

    close_idx = _find_last_unescaped(rule_string, ")")
    if close_idx == -1 or close_idx <= open_idx:
        return {"toolName": normalize_legacy_tool_name(rule_string)}

    if close_idx != len(rule_string) - 1:
        return {"toolName": normalize_legacy_tool_name(rule_string)}

    tool_name = rule_string[:open_idx]
    raw_content = rule_string[open_idx + 1 : close_idx]

    if not tool_name:
        return {"toolName": normalize_legacy_tool_name(rule_string)}

    if raw_content in ("", "*"):
        return {"toolName": normalize_legacy_tool_name(tool_name)}

    return {
        "toolName": normalize_legacy_tool_name(tool_name),
        "ruleContent": unescape_rule_content(raw_content),
    }


def permission_rule_value_to_string(rule_value: PermissionRuleValue) -> str:
    """Serialize a permission rule value to its canonical string form.

    >>> permission_rule_value_to_string({'toolName': 'Bash'})
    'Bash'
    >>> permission_rule_value_to_string({'toolName': 'Bash', 'ruleContent': 'npm install'})
    'Bash(npm install)'
    """
    rule_content = rule_value.get("ruleContent")
    if not rule_content:
        return rule_value["toolName"]
    escaped = escape_rule_content(rule_content)
    return f"{rule_value['toolName']}({escaped})"

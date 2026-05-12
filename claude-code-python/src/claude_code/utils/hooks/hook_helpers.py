"""
Hook helpers - shared utilities for hook handling.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Union

DEFAULT_HOOK_SHELL = "bash"


def is_hook_equal(
    a: Union[Dict[str, Any], Any],
    b: Union[Dict[str, Any], Any],
) -> bool:
    """Check if two hooks are equal (comparing only command/prompt content, not timeout)."""
    a_type = a.get("type") if isinstance(a, dict) else getattr(a, "type", None)
    b_type = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)

    if a_type != b_type:
        return False

    def get(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def same_if(x: Any, y: Any) -> bool:
        return (get(x, "if", "") or "") == (get(y, "if", "") or "")

    if a_type == "command":
        return (
            get(a, "command") == get(b, "command")
            and (get(a, "shell") or DEFAULT_HOOK_SHELL) == (get(b, "shell") or DEFAULT_HOOK_SHELL)
            and same_if(a, b)
        )
    elif a_type == "prompt":
        return get(a, "prompt") == get(b, "prompt") and same_if(a, b)
    elif a_type == "agent":
        return get(a, "prompt") == get(b, "prompt") and same_if(a, b)
    elif a_type == "http":
        return get(a, "url") == get(b, "url") and same_if(a, b)
    elif a_type == "function":
        # Function hooks can't be compared (no stable identifier)
        return False
    return False


def get_hook_display_text(hook: Union[Dict[str, Any], Any]) -> str:
    """Get the display text for a hook."""
    status_message = (
        hook.get("statusMessage") if isinstance(hook, dict)
        else getattr(hook, "status_message", None)
    )
    if status_message:
        return status_message

    hook_type = hook.get("type") if isinstance(hook, dict) else getattr(hook, "type", None)

    def get(key: str, default: str = "") -> str:
        if isinstance(hook, dict):
            return hook.get(key, default)
        return getattr(hook, key, default)

    if hook_type == "command":
        return get("command")
    elif hook_type == "prompt":
        return get("prompt")
    elif hook_type == "agent":
        return get("prompt")
    elif hook_type == "http":
        return get("url")
    elif hook_type in ("callback", "function"):
        return hook_type
    return ""


def add_arguments_to_prompt(prompt: str, json_input: str) -> str:
    """Add hook input JSON to prompt, replacing $ARGUMENTS placeholder or appending."""
    from ..argument_substitution import substitute_arguments
    return substitute_arguments(prompt, json_input)


def hook_source_description_display_string(source: str) -> str:
    """Get a description string for a hook source."""
    mapping = {
        "userSettings": "User settings (~/.claude/settings.json)",
        "projectSettings": "Project settings (.claude/settings.json)",
        "localSettings": "Local settings (.claude/settings.local.json)",
        "pluginHook": "Plugin hooks (~/.claude/plugins/*/hooks/hooks.json)",
        "sessionHook": "Session hooks (in-memory, temporary)",
        "builtinHook": "Built-in hooks (registered internally by Claude Code)",
    }
    return mapping.get(source, source)


def hook_source_header_display_string(source: str) -> str:
    """Get a header display string for a hook source."""
    mapping = {
        "userSettings": "User Settings",
        "projectSettings": "Project Settings",
        "localSettings": "Local Settings",
        "pluginHook": "Plugin Hooks",
        "sessionHook": "Session Hooks",
        "builtinHook": "Built-in Hooks",
    }
    return mapping.get(source, source)


def hook_source_inline_display_string(source: str) -> str:
    """Get an inline display string for a hook source."""
    mapping = {
        "userSettings": "User",
        "projectSettings": "Project",
        "localSettings": "Local",
        "pluginHook": "Plugin",
        "sessionHook": "Session",
        "builtinHook": "Built-in",
    }
    return mapping.get(source, source)


def get_rule_behavior_description(behavior: str) -> str:
    """Get prose description for rule behavior."""
    if behavior == "allow":
        return "allowed"
    elif behavior == "deny":
        return "denied"
    return "asked for confirmation for"

"""
Plugin policy - evaluates plugin installation and usage policies.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def is_plugin_install_allowed(plugin_id: str) -> bool:
    """Check if installing a plugin is allowed by policy."""
    try:
        from .plugin_blocklist import is_plugin_blocked
        if is_plugin_blocked(plugin_id):
            return False

        from .managed_plugins import is_plugin_management_locked, get_managed_enabled_plugins
        if is_plugin_management_locked():
            # Only allow plugins explicitly listed in managed settings
            managed = get_managed_enabled_plugins()
            return managed is None or plugin_id in managed

        return True
    except Exception:
        return True


def get_policy_violation_reason(plugin_id: str) -> Optional[str]:
    """Get the reason a plugin is not allowed by policy, or None if allowed."""
    try:
        from .plugin_blocklist import is_plugin_blocked
        if is_plugin_blocked(plugin_id):
            return f"Plugin '{plugin_id}' is on the blocklist"

        from .managed_plugins import is_plugin_management_locked, get_managed_enabled_plugins
        if is_plugin_management_locked():
            managed = get_managed_enabled_plugins()
            if managed is not None and plugin_id not in managed:
                return (
                    f"Plugin '{plugin_id}' is not in the enterprise-managed enabled list"
                )

        return None
    except Exception:
        return None


def enforce_plugin_policy(plugin_id: str) -> None:
    """Raise an error if plugin installation violates policy."""
    reason = get_policy_violation_reason(plugin_id)
    if reason:
        raise PermissionError(reason)

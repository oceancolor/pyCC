"""
Managed plugins - handles managed (policy-controlled) plugin settings.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


def get_managed_plugin_settings() -> Dict[str, Any]:
    """Get managed plugin settings from policy."""
    try:
        from ..settings.settings import get_settings_for_source
        policy = get_settings_for_source("policySettings")
        if policy is None:
            return {}
        return policy.get("plugins") or {}
    except Exception:
        return {}


def get_managed_enabled_plugins() -> Optional[List[str]]:
    """Get the list of managed-enabled plugins, or None if not restricted."""
    settings = get_managed_plugin_settings()
    return settings.get("enabledPlugins")


def is_plugin_managed_enabled(plugin_id: str) -> bool:
    """Check if a plugin is in the managed enabled list."""
    enabled = get_managed_enabled_plugins()
    if enabled is None:
        return True  # No restriction
    return plugin_id in enabled


def is_plugin_management_locked() -> bool:
    """Check if plugin management is locked to managed sources only."""
    try:
        from ..settings.plugin_only_policy import is_restricted_to_plugin_only
        return is_restricted_to_plugin_only("plugins")
    except Exception:
        return False

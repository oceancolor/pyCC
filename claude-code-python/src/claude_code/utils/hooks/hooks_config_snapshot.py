"""
Hooks config snapshot - captures and manages the hooks configuration snapshot.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

_initial_hooks_config: Optional[Dict[str, Any]] = None


def _get_hooks_from_allowed_sources() -> Dict[str, Any]:
    """Get hooks from allowed sources respecting policy settings."""
    try:
        from ..settings.settings import get_settings_for_source, get_settings_deprecated
        from ..settings.plugin_only_policy import is_restricted_to_plugin_only

        policy_settings = get_settings_for_source("policySettings")

        if policy_settings and policy_settings.get("disableAllHooks") is True:
            return {}

        if policy_settings and policy_settings.get("allowManagedHooksOnly") is True:
            return policy_settings.get("hooks") or {}

        if is_restricted_to_plugin_only("hooks"):
            return (policy_settings or {}).get("hooks") or {}

        merged = get_settings_deprecated()
        if merged.get("disableAllHooks") is True:
            return (policy_settings or {}).get("hooks") or {}

        return merged.get("hooks") or {}
    except Exception:
        return {}


def should_allow_managed_hooks_only() -> bool:
    """Check if only managed hooks should run."""
    try:
        from ..settings.settings import get_settings_for_source, get_settings_deprecated
        policy_settings = get_settings_for_source("policySettings")
        if policy_settings and policy_settings.get("allowManagedHooksOnly") is True:
            return True
        merged = get_settings_deprecated()
        if (
            merged.get("disableAllHooks") is True
            and (policy_settings or {}).get("disableAllHooks") is not True
        ):
            return True
        return False
    except Exception:
        return False


def should_disable_all_hooks_including_managed() -> bool:
    """Check if all hooks (including managed) should be disabled."""
    try:
        from ..settings.settings import get_settings_for_source
        policy = get_settings_for_source("policySettings")
        return bool(policy and policy.get("disableAllHooks") is True)
    except Exception:
        return False


def capture_hooks_config_snapshot() -> None:
    """Capture a snapshot of the current hooks configuration."""
    global _initial_hooks_config
    _initial_hooks_config = _get_hooks_from_allowed_sources()


def update_hooks_config_snapshot() -> None:
    """Update the hooks configuration snapshot."""
    global _initial_hooks_config
    try:
        from ..settings.settings_cache import reset_settings_cache
        reset_settings_cache()
    except Exception:
        pass
    _initial_hooks_config = _get_hooks_from_allowed_sources()


def get_hooks_config_from_snapshot() -> Optional[Dict[str, Any]]:
    """Get the current hooks configuration from snapshot."""
    global _initial_hooks_config
    if _initial_hooks_config is None:
        capture_hooks_config_snapshot()
    return _initial_hooks_config


def reset_hooks_config_snapshot() -> None:
    """Reset the hooks configuration snapshot (useful for testing)."""
    global _initial_hooks_config
    _initial_hooks_config = None

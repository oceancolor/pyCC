"""
Plugin only policy - check if customization surfaces are locked to plugin-only sources.
"""

from __future__ import annotations

from typing import Optional, Set, Union

ADMIN_TRUSTED_SOURCES: Set[str] = {
    "plugin",
    "policySettings",
    "built-in",
    "builtin",
    "bundled",
}


def is_restricted_to_plugin_only(surface: str) -> bool:
    """
    Check whether a customization surface is locked to plugin-only sources
    by the managed strictPluginOnlyCustomization policy.
    """
    try:
        from .settings import get_settings_for_source
        policy = get_settings_for_source("policySettings")
        if policy is None:
            return False
        strict = policy.get("strictPluginOnlyCustomization")
        if strict is True:
            return True
        if isinstance(strict, list):
            return surface in strict
        return False
    except Exception:
        return False


def is_source_admin_trusted(source: Optional[str]) -> bool:
    """
    Whether a customization's source is admin-trusted under strictPluginOnlyCustomization.
    """
    return source is not None and source in ADMIN_TRUSTED_SOURCES

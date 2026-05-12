"""
All errors - combines settings and MCP validation errors.
"""

from __future__ import annotations

from typing import Any, Dict, List


class SettingsWithErrors:
    def __init__(self, settings: Dict[str, Any], errors: List[Any]) -> None:
        self.settings = settings
        self.errors = errors


def get_settings_with_all_errors() -> SettingsWithErrors:
    """
    Get merged settings with all validation errors, including MCP config errors.
    """
    try:
        from .validation import get_settings_with_errors
        result = get_settings_with_errors()
    except Exception:
        result = SettingsWithErrors(settings={}, errors=[])

    try:
        from ...services.mcp.config import get_mcp_configs_by_scope
        mcp_errors = []
        for scope in ["user", "project", "local"]:
            try:
                config_result = get_mcp_configs_by_scope(scope)
                mcp_errors.extend(config_result.errors)
            except Exception:
                pass
        return SettingsWithErrors(
            settings=result.settings,
            errors=result.errors + mcp_errors,
        )
    except Exception:
        return result

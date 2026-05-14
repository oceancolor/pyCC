"""Plugins service sub-package.

Provides plugin installation management, CLI command registration, and
plugin operations (install, uninstall, update) for Claude Code extensions.
"""
from __future__ import annotations

from claude_code.services.plugins.plugin_installation_manager import (
    InstallationStatus,
    PluginInstallStatus,
)
from claude_code.services.plugins.plugin_operations import (
    PluginOperationResult,
    is_installable_scope,
)

__all__ = [
    "PluginInstallStatus",
    "InstallationStatus",
    "PluginOperationResult",
    "is_installable_scope",
]

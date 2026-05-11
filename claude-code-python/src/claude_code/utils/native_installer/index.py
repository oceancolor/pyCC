"""
Native Installer - Public API

This is the barrel file that exports only the functions actually used by external modules.
External modules should only import from this file.
"""
from .installer import (
    SetupMessage,
    check_install,
    cleanup_npm_installations,
    cleanup_old_versions,
    cleanup_shell_aliases,
    install_latest,
    lock_current_version,
    remove_installed_symlink,
)

__all__ = [
    "SetupMessage",
    "check_install",
    "cleanup_npm_installations",
    "cleanup_old_versions",
    "cleanup_shell_aliases",
    "install_latest",
    "lock_current_version",
    "remove_installed_symlink",
]

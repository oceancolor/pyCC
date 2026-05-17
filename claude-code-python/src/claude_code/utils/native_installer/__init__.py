"""Native installer utilities sub-package. Ported from utils/nativeInstaller/.

Provides helpers for downloading and installing native binaries (e.g. tree-sitter
parsers, native extensions) required by Claude Code.
"""
from __future__ import annotations

from claude_code.utils.native_installer.package_managers import get_platform
from claude_code.utils.native_installer.pid_lock import (
    VersionLockContent,
    is_pid_based_locking_enabled,
)
from claude_code.utils.native_installer.installer import (
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
    # package_managers
    "get_platform",
    # pid_lock
    "is_pid_based_locking_enabled",
    "VersionLockContent",
    # installer
    "SetupMessage",
    "check_install",
    "cleanup_npm_installations",
    "cleanup_old_versions",
    "cleanup_shell_aliases",
    "install_latest",
    "lock_current_version",
    "remove_installed_symlink",
]

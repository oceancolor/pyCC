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

__all__ = [
    "get_platform",
    "is_pid_based_locking_enabled",
    "VersionLockContent",
]

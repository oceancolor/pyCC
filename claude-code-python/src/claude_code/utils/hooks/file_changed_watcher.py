"""
File changed watcher - watches files and triggers CwdChanged/FileChanged hooks.
"""

from __future__ import annotations

import os
from typing import Any, Callable, List, Optional

_initialized = False
_current_cwd = ""
_dynamic_watch_paths: List[str] = []
_has_env_hooks = False
_notify_callback: Optional[Callable[[str, bool], None]] = None


def set_env_hook_notifier(cb: Optional[Callable[[str, bool], None]]) -> None:
    """Set a callback for environment hook notifications."""
    global _notify_callback
    _notify_callback = cb


def initialize_file_changed_watcher(cwd: str) -> None:
    """Initialize the file changed watcher."""
    global _initialized, _current_cwd, _has_env_hooks
    if _initialized:
        return
    _initialized = True
    _current_cwd = cwd

    try:
        from .hooks_config_snapshot import get_hooks_config_from_snapshot
        config = get_hooks_config_from_snapshot()
        _has_env_hooks = (
            len(config.get("CwdChanged", []) if config else []) > 0
            or len(config.get("FileChanged", []) if config else []) > 0
        )
    except Exception:
        _has_env_hooks = False


def dispose_file_changed_watcher() -> None:
    """Dispose the file changed watcher."""
    global _initialized
    _initialized = False


def update_dynamic_watch_paths(paths: List[str]) -> None:
    """Update the dynamic watch paths from hook output."""
    global _dynamic_watch_paths
    _dynamic_watch_paths = paths


def reset_file_changed_watcher() -> None:
    """Reset the watcher state (for testing)."""
    global _initialized, _current_cwd, _dynamic_watch_paths, _has_env_hooks, _notify_callback
    _initialized = False
    _current_cwd = ""
    _dynamic_watch_paths = []
    _has_env_hooks = False
    _notify_callback = None

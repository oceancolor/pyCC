"""
Managed path - resolves settings file paths for each source.
"""

from __future__ import annotations

import os
from typing import Optional


_CLAUDE_DIR = os.path.expanduser("~/.claude")
_PROJECT_SETTINGS_FILENAME = ".claude/settings.json"
_PROJECT_LOCAL_SETTINGS_FILENAME = ".claude/settings.local.json"


def get_user_settings_path() -> str:
    """Get the path to the user settings file."""
    return os.path.join(_CLAUDE_DIR, "settings.json")


def get_project_settings_path(cwd: Optional[str] = None) -> str:
    """Get the path to the project settings file."""
    base = cwd or os.getcwd()
    return os.path.join(base, _PROJECT_SETTINGS_FILENAME)


def get_project_local_settings_path(cwd: Optional[str] = None) -> str:
    """Get the path to the project-local settings file."""
    base = cwd or os.getcwd()
    return os.path.join(base, _PROJECT_LOCAL_SETTINGS_FILENAME)


def get_managed_settings_path() -> Optional[str]:
    """Get the path to the managed (policy) settings file."""
    # Check environment variable first
    env_path = os.environ.get("CLAUDE_CODE_MANAGED_SETTINGS_PATH")
    if env_path:
        return env_path

    # Check standard managed settings locations
    candidates = [
        "/Library/Application Support/ClaudeCode/managed_settings.json",  # macOS
        "/etc/claude-code/managed_settings.json",  # Linux
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate

    return None


def ensure_dir_exists(path: str) -> None:
    """Ensure the directory for a settings file exists."""
    os.makedirs(os.path.dirname(path), exist_ok=True)

"""
Settings constants - source names and display strings.
"""

from __future__ import annotations

from typing import List, Optional

SETTING_SOURCES = [
    "userSettings",
    "projectSettings",
    "localSettings",
    "flagSettings",
    "policySettings",
]

SettingSource = str
EditableSettingSource = str  # userSettings | projectSettings | localSettings

SOURCES = [
    "localSettings",
    "projectSettings",
    "userSettings",
]

CLAUDE_CODE_SETTINGS_SCHEMA_URL = (
    "https://json.schemastore.org/claude-code-settings.json"
)


def get_setting_source_name(source: SettingSource) -> str:
    mapping = {
        "userSettings": "user",
        "projectSettings": "project",
        "localSettings": "project, gitignored",
        "flagSettings": "cli flag",
        "policySettings": "managed",
    }
    return mapping.get(source, source)


def get_source_display_name(source: str) -> str:
    mapping = {
        "userSettings": "User",
        "projectSettings": "Project",
        "localSettings": "Local",
        "flagSettings": "Flag",
        "policySettings": "Managed",
        "plugin": "Plugin",
        "built-in": "Built-in",
    }
    return mapping.get(source, source)


def get_setting_source_display_name_lowercase(source: str) -> str:
    mapping = {
        "userSettings": "user settings",
        "projectSettings": "shared project settings",
        "localSettings": "project local settings",
        "flagSettings": "command line arguments",
        "policySettings": "enterprise managed settings",
        "cliArg": "CLI argument",
        "command": "command configuration",
        "session": "current session",
    }
    return mapping.get(source, source)


def get_setting_source_display_name_capitalized(source: str) -> str:
    mapping = {
        "userSettings": "User settings",
        "projectSettings": "Shared project settings",
        "localSettings": "Project local settings",
        "flagSettings": "Command line arguments",
        "policySettings": "Enterprise managed settings",
        "cliArg": "CLI argument",
        "command": "Command configuration",
        "session": "Current session",
    }
    return mapping.get(source, source)


def parse_setting_sources_flag(flag: str) -> List[SettingSource]:
    """Parse the --setting-sources CLI flag into SettingSource list."""
    if not flag:
        return []
    result = []
    name_map = {"user": "userSettings", "project": "projectSettings", "local": "localSettings"}
    for name in flag.split(","):
        name = name.strip()
        if name not in name_map:
            raise ValueError(
                f"Invalid setting source: {name}. Valid options are: user, project, local"
            )
        result.append(name_map[name])
    return result


def get_enabled_setting_sources() -> List[SettingSource]:
    """Get enabled setting sources with policy/flag always included."""
    try:
        from ...bootstrap.state import get_allowed_setting_sources
        allowed = set(get_allowed_setting_sources())
    except Exception:
        allowed = set(SETTING_SOURCES[:3])  # user, project, local by default
    allowed.add("policySettings")
    allowed.add("flagSettings")
    return list(allowed)


def is_setting_source_enabled(source: SettingSource) -> bool:
    """Check if a specific source is enabled."""
    return source in get_enabled_setting_sources()

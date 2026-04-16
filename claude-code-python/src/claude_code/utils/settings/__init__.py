"""
Settings/configuration system
原始 TS: src/utils/settings/ + src/utils/config.ts (partial)

zod → pydantic
file-based JSON settings
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from pydantic import BaseModel, Field, model_validator

from claude_code.utils.env_utils import get_claude_config_home_dir


# ---------------------------------------------------------------------------
# Settings schema (Pydantic)
# ---------------------------------------------------------------------------

class McpServerStdioConfig(BaseModel):
    type: str = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_ms: Optional[int] = None
    disabled: Optional[bool] = None


class McpServerHttpConfig(BaseModel):
    type: str = "http"
    url: str = ""
    headers: dict[str, str] = Field(default_factory=dict)
    timeout_ms: Optional[int] = None
    disabled: Optional[bool] = None


McpServerConfig = Union[McpServerStdioConfig, McpServerHttpConfig]


class SettingsJson(BaseModel):
    """
    User/project settings schema.
    原始 TS: SettingsJson / SettingsSchema (zod)
    """
    model: Optional[str] = None
    small_fast_model: Optional[str] = Field(None, alias="smallFastModel")
    theme: Optional[str] = None
    verbose: Optional[bool] = None
    shell: Optional[str] = None
    api_key: Optional[str] = Field(None, alias="apiKey")
    api_key_helper: Optional[str] = Field(None, alias="apiKeyHelper")
    max_tokens: Optional[int] = Field(None, alias="maxTokens")
    allowed_tools: list[str] = Field(default_factory=list, alias="allowedTools")
    disallowed_tools: list[str] = Field(default_factory=list, alias="disallowedTools")
    mcp_servers: dict[str, Any] = Field(default_factory=dict, alias="mcpServers")
    permissions: dict[str, Any] = Field(default_factory=dict)
    hooks: dict[str, Any] = Field(default_factory=dict)
    env: dict[str, str] = Field(default_factory=dict)
    disable_auto_updater: Optional[bool] = Field(None, alias="disableAutoUpdater")
    disable_non_essential_traffic: Optional[bool] = Field(
        None, alias="disableNonEssentialTraffic"
    )
    auto_memory_enabled: Optional[bool] = Field(None, alias="autoMemoryEnabled")

    model_config = {"populate_by_name": True, "extra": "allow"}


# ---------------------------------------------------------------------------
# Config file paths
# ---------------------------------------------------------------------------

def get_global_settings_path() -> str:
    """Path to global user settings file."""
    return os.path.join(get_claude_config_home_dir(), "settings.json")


def get_local_settings_path() -> str:
    """Path to local (project) settings file."""
    return os.path.join(os.getcwd(), ".claude", "settings.json")


def get_project_settings_path(project_root: Optional[str] = None) -> str:
    """Path to project settings file."""
    root = project_root or os.getcwd()
    return os.path.join(root, ".claude", "settings.json")


# ---------------------------------------------------------------------------
# Settings loading
# ---------------------------------------------------------------------------

def _read_json_file(path: str) -> Optional[dict[str, Any]]:
    """Read and parse a JSON file, returning None on error."""
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read().lstrip("\ufeff")  # strip BOM
        return json.loads(content)
    except (OSError, json.JSONDecodeError):
        return None


def load_settings(path: str) -> Optional[SettingsJson]:
    """Load settings from a JSON file path."""
    data = _read_json_file(path)
    if data is None:
        return None
    try:
        return SettingsJson.model_validate(data)
    except Exception:
        return None


def get_global_settings() -> SettingsJson:
    """Get the global user settings, returning defaults if not found."""
    path = get_global_settings_path()
    return load_settings(path) or SettingsJson()


def get_project_settings(project_root: Optional[str] = None) -> SettingsJson:
    """Get project-level settings, returning defaults if not found."""
    path = get_project_settings_path(project_root)
    return load_settings(path) or SettingsJson()


def merge_settings(*settings_list: SettingsJson) -> SettingsJson:
    """
    Merge multiple SettingsJson objects, with later values taking precedence.
    原始 TS: mergeWith (lodash) with settingsMergeCustomizer
    """
    merged: dict[str, Any] = {}
    for s in settings_list:
        data = s.model_dump(exclude_none=True, by_alias=True)
        # Special handling for list fields: concat instead of replace
        for key in ("allowedTools", "disallowedTools"):
            if key in data and key in merged:
                merged[key] = list({*merged[key], *data[key]})
                continue
        merged.update(data)
    return SettingsJson.model_validate(merged)


# ---------------------------------------------------------------------------
# Project config (from .claude/settings.json)
# ---------------------------------------------------------------------------

@dataclass
class ProjectConfig:
    """
    Project-level configuration.
    原始 TS: ProjectConfig
    """
    allowed_tools: list[str] = field(default_factory=list)
    mcp_context_uris: list[str] = field(default_factory=list)
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    last_api_duration: Optional[int] = None
    has_trust_dialog_accepted: Optional[bool] = None
    has_cwd_trust_dialog_accepted: Optional[bool] = None
    ignore_patterns: list[str] = field(default_factory=list)
    project_memory_hashes: dict[str, str] = field(default_factory=dict)
    enabled_mcps: list[str] = field(default_factory=list)
    disabled_mcps: list[str] = field(default_factory=list)

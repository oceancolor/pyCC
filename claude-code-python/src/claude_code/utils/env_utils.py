"""
Environment utility functions
原始 TS: src/utils/envUtils.ts
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional, Union


@lru_cache(maxsize=None)
def _get_claude_config_home_dir_cached(config_dir_override: Optional[str]) -> str:
    """Internal cached implementation."""
    base = config_dir_override or str(Path.home() / ".claude")
    # Python equivalent of NFC normalization (unicode normalization)
    import unicodedata
    return unicodedata.normalize("NFC", base)


def get_claude_config_home_dir() -> str:
    """
    Returns the Claude config home directory.
    Respects CLAUDE_CONFIG_DIR environment variable.
    原始 TS: getClaudeConfigHomeDir (memoized)
    """
    return _get_claude_config_home_dir_cached(os.environ.get("CLAUDE_CONFIG_DIR"))


def get_teams_dir() -> str:
    return os.path.join(get_claude_config_home_dir(), "teams")


def is_env_truthy(env_var: Union[str, bool, None]) -> bool:
    """Check if an env var value is truthy."""
    if not env_var:
        return False
    if isinstance(env_var, bool):
        return env_var
    return env_var.lower().strip() in ("1", "true", "yes", "on")


def is_env_defined_falsy(env_var: Union[str, bool, None]) -> bool:
    """Check if an env var value is explicitly falsy."""
    if env_var is None:
        return False
    if isinstance(env_var, bool):
        return not env_var
    if not env_var:
        return False
    return env_var.lower().strip() in ("0", "false", "no", "off")


def is_bare_mode() -> bool:
    """
    Check if running in bare mode (--bare / CLAUDE_CODE_SIMPLE).
    Skips hooks, LSP, plugin sync, etc.
    """
    return (
        is_env_truthy(os.environ.get("CLAUDE_CODE_SIMPLE"))
        or "--bare" in sys.argv
    )


def parse_env_vars(raw_env_args: Optional[list[str]]) -> dict[str, str]:
    """Parse an array of KEY=VALUE env var strings into a dict."""
    parsed: dict[str, str] = {}
    if raw_env_args:
        for env_str in raw_env_args:
            if "=" not in env_str:
                raise ValueError(
                    f"Invalid environment variable format: {env_str}, "
                    "environment variables should be added as: -e KEY1=value1 -e KEY2=value2"
                )
            key, _, value = env_str.partition("=")
            if not key:
                raise ValueError(
                    f"Invalid environment variable format: {env_str}"
                )
            parsed[key] = value
    return parsed


def get_aws_region() -> str:
    """Get the AWS region with fallback to default."""
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


def get_default_vertex_region() -> str:
    """Get the default Vertex AI region."""
    return os.environ.get("CLOUD_ML_REGION", "us-east5")


# Model prefix → env var for Vertex region overrides
_VERTEX_REGION_OVERRIDES: list[tuple[str, str]] = [
    ("claude-haiku-4-5", "VERTEX_REGION_CLAUDE_HAIKU_4_5"),
    ("claude-3-5-haiku", "VERTEX_REGION_CLAUDE_3_5_HAIKU"),
    ("claude-3-5-sonnet", "VERTEX_REGION_CLAUDE_3_5_SONNET"),
    ("claude-3-7-sonnet", "VERTEX_REGION_CLAUDE_3_7_SONNET"),
    ("claude-opus-4-1", "VERTEX_REGION_CLAUDE_4_1_OPUS"),
    ("claude-opus-4", "VERTEX_REGION_CLAUDE_4_0_OPUS"),
    ("claude-sonnet-4-6", "VERTEX_REGION_CLAUDE_4_6_SONNET"),
    ("claude-sonnet-4-5", "VERTEX_REGION_CLAUDE_4_5_SONNET"),
    ("claude-sonnet-4", "VERTEX_REGION_CLAUDE_4_0_SONNET"),
]


def get_vertex_region_for_model(model: Optional[str]) -> str:
    """Get the Vertex AI region for a specific model."""
    if model:
        for prefix, env_var in _VERTEX_REGION_OVERRIDES:
            if model.startswith(prefix):
                return os.environ.get(env_var) or get_default_vertex_region()
    return get_default_vertex_region()


def is_running_on_homespace() -> bool:
    """Check if running on Homespace (ant-internal cloud environment)."""
    return (
        os.environ.get("USER_TYPE") == "ant"
        and is_env_truthy(os.environ.get("COO_RUNNING_ON_HOMESPACE"))
    )

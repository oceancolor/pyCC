"""
Managed environment utilities for Claude Code.

Handles environment variable management from settings sources with proper
filtering for SSH tunnels, host-managed providers, and CCD spawn env vars.

Key concerns:
- SSH tunnel vars must not be overridden by user settings
- Host-managed provider vars must not be overridden when CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST is set
- CCD spawn-env keys captured before settings are applied must not be overridden
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Set

# ---------------------------------------------------------------------------
# Provider-managed env var detection
# ---------------------------------------------------------------------------

# Env vars that route provider/model selection — must not be overridden
# when the host controls inference routing.
_PROVIDER_MANAGED_PREFIXES = (
    "ANTHROPIC_MODEL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_PROVIDER",
    "ANTHROPIC_BASE_URL",
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "VERTEX_REGION",
    "VERTEX_PROJECT_ID",
)

# Safe env vars that project-scoped settings are allowed to set
SAFE_ENV_VARS: Set[str] = {
    "ANTHROPIC_TIMEOUT",
    "ANTHROPIC_MAX_RETRIES",
    "CLAUDE_CODE_MAX_OUTPUT_TOKENS",
    "BASH_MAX_TIMEOUT_MS",
    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "NO_PROXY",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
    "NODE_EXTRA_CA_CERTS",
}

# SSH tunnel env vars that user settings must never clobber
_SSH_TUNNEL_VARS = frozenset(
    {
        "ANTHROPIC_UNIX_SOCKET",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_OAUTH_TOKEN",
    }
)

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------

# CCD spawn-env keys snapshot — captured once before any settings are applied
_ccd_spawn_env_keys: Optional[Set[str]] = None  # None = not yet captured
_ccd_spawn_env_initialized: bool = False


def _is_env_truthy(value: Optional[str]) -> bool:
    return bool(value and value.lower() not in ("0", "false", "no", ""))


def is_provider_managed_env_var(key: str) -> bool:
    """Return True if *key* is a provider-routing variable."""
    upper = key.upper()
    return any(upper.startswith(prefix) for prefix in _PROVIDER_MANAGED_PREFIXES)


# ---------------------------------------------------------------------------
# Filter helpers (mirror TS withoutXxx functions)
# ---------------------------------------------------------------------------

def _without_ssh_tunnel_vars(
    env: Optional[Dict[str, str]]
) -> Dict[str, str]:
    """Strip SSH tunnel vars if ANTHROPIC_UNIX_SOCKET is active."""
    if not env or not os.environ.get("ANTHROPIC_UNIX_SOCKET"):
        return env or {}
    return {k: v for k, v in env.items() if k not in _SSH_TUNNEL_VARS}


def _without_host_managed_provider_vars(
    env: Optional[Dict[str, str]]
) -> Dict[str, str]:
    """Strip provider-routing vars when the host controls inference."""
    if not env:
        return {}
    if not _is_env_truthy(os.environ.get("CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST")):
        return env
    return {k: v for k, v in env.items() if not is_provider_managed_env_var(k)}


def _without_ccd_spawn_env_keys(
    env: Optional[Dict[str, str]]
) -> Dict[str, str]:
    """Strip keys that were in the CCD spawn-env snapshot."""
    if not env or not _ccd_spawn_env_keys:
        return env or {}
    return {k: v for k, v in env.items() if k not in _ccd_spawn_env_keys}


def filter_settings_env(env: Optional[Dict[str, str]]) -> Dict[str, str]:
    """Compose all strip filters applied to every settings-sourced env dict."""
    return _without_ccd_spawn_env_keys(
        _without_host_managed_provider_vars(
            _without_ssh_tunnel_vars(env)
        )
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_managed_env() -> bool:
    """
    Return True if running inside a managed/hosted Claude Code environment.

    Checks CLAUDE_CODE_REMOTE and CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST.
    """
    return _is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE")) or _is_env_truthy(
        os.environ.get("CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST")
    )


def get_managed_env_info() -> Dict[str, object]:
    """Return a dict describing the current managed environment."""
    return {
        "is_managed": is_managed_env(),
        "is_remote": _is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE")),
        "provider_managed_by_host": _is_env_truthy(
            os.environ.get("CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST")
        ),
        "entrypoint": os.environ.get("CLAUDE_CODE_ENTRYPOINT"),
        "ssh_tunnel_active": bool(os.environ.get("ANTHROPIC_UNIX_SOCKET")),
        "github_actions": _is_env_truthy(os.environ.get("GITHUB_ACTIONS")),
    }


def apply_safe_config_environment_variables(
    global_config_env: Optional[Dict[str, str]] = None,
    settings_env: Optional[Dict[str, str]] = None,
) -> None:
    """
    Apply environment variables from trusted/safe settings sources.

    - global_config_env: from ~/.claude.json (user-controlled)
    - settings_env: merged settings; only SAFE_ENV_VARS keys applied

    Mirrors TS applySafeConfigEnvironmentVariables().
    """
    global _ccd_spawn_env_keys, _ccd_spawn_env_initialized

    # Capture CCD spawn-env keys before any settings.env is applied (once)
    if not _ccd_spawn_env_initialized:
        _ccd_spawn_env_initialized = True
        if os.environ.get("CLAUDE_CODE_ENTRYPOINT") == "claude-desktop":
            _ccd_spawn_env_keys = set(os.environ.keys())
        else:
            _ccd_spawn_env_keys = None

    if global_config_env:
        os.environ.update(filter_settings_env(global_config_env))

    if settings_env:
        filtered = filter_settings_env(settings_env)
        for key, value in filtered.items():
            if key.upper() in SAFE_ENV_VARS:
                os.environ[key] = value


def apply_config_environment_variables(
    global_config_env: Optional[Dict[str, str]] = None,
    settings_env: Optional[Dict[str, str]] = None,
) -> None:
    """
    Apply ALL (non-filtered) environment variables after trust is established.

    Mirrors TS applyConfigEnvironmentVariables().
    """
    if global_config_env:
        os.environ.update(filter_settings_env(global_config_env))
    if settings_env:
        os.environ.update(filter_settings_env(settings_env))

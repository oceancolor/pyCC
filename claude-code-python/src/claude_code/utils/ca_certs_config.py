"""
ca_certs_config.py - CA certificate configuration from settings/config.

Ported from caCertsConfig.ts.

Reads NODE_EXTRA_CA_CERTS (or its Python equivalent SSL_CERT_FILE /
REQUESTS_CA_BUNDLE) from the user's settings files and populates the
environment early in init — before any TLS connections are made.

Settings sources (in precedence order, highest first):
  1. ~/.claude/settings.json   (userSettings)
  2. ~/.claude.json            (globalConfig)

Only user-controlled files are read here — project-level settings are
NOT consulted to prevent malicious repos from injecting CA certs before
a trust dialog.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Environment variable name (mirrors Node.js convention)
_CA_CERTS_ENV_VAR = "NODE_EXTRA_CA_CERTS"


def _log_debug(msg: str) -> None:
    logger.debug("CA certs: %s", msg)


def _read_json_safe(path: Path) -> Optional[dict]:
    """Read a JSON file, returning None on any error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _get_extra_certs_path_from_config() -> Optional[str]:
    """
    Read NODE_EXTRA_CA_CERTS from ~/.claude/settings.json or ~/.claude.json.
    Returns the path string, or None if not found / on error.
    """
    home = Path.home()
    global_config_path = home / ".claude.json"
    user_settings_path = home / ".claude" / "settings.json"

    global_config = _read_json_safe(global_config_path)
    user_settings = _read_json_safe(user_settings_path)

    global_env: dict = (global_config or {}).get("env", {}) or {}
    settings_env: dict = (user_settings or {}).get("env", {}) or {}

    _log_debug(
        f"Config fallback - globalEnv keys: {list(global_env) or 'none'}, "
        f"settingsEnv keys: {list(settings_env) or 'none'}"
    )

    # Settings override global config (same precedence as TS)
    path: Optional[str] = (
        settings_env.get(_CA_CERTS_ENV_VAR)
        or global_env.get(_CA_CERTS_ENV_VAR)
    )
    if path:
        _log_debug(f"Found {_CA_CERTS_ENV_VAR} in config/settings: {path}")
    return path


def apply_extra_ca_certs_from_config() -> None:
    """
    Populate ``NODE_EXTRA_CA_CERTS`` in ``os.environ`` from settings/config,
    if it is not already set.

    Call this early in process startup — before any HTTPS connections — so
    that the TLS stack picks up the custom CA certificate.
    """
    if os.environ.get(_CA_CERTS_ENV_VAR):
        return  # Already set in environment, nothing to do

    config_path = _get_extra_certs_path_from_config()
    if config_path:
        os.environ[_CA_CERTS_ENV_VAR] = config_path
        _log_debug(f"Applied {_CA_CERTS_ENV_VAR} from config to os.environ: {config_path}")


def get_extra_ca_certs_path() -> Optional[str]:
    """
    Return the effective NODE_EXTRA_CA_CERTS path: from the environment if
    already set, otherwise from settings/config.
    """
    return os.environ.get(_CA_CERTS_ENV_VAR) or _get_extra_certs_path_from_config()

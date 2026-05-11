"""
Shared utilities for spawning teammates across different backends.

原始 TS: utils/swarm/spawnUtils.ts
"""

import os
import shlex
import sys
from typing import List

from .backends.teammate_mode_snapshot import get_teammate_mode_from_snapshot
from .constants import TEAMMATE_COMMAND_ENV_VAR


def get_teammate_command() -> str:
    """Get the command to use for spawning teammate processes.

    Uses TEAMMATE_COMMAND_ENV_VAR if set, otherwise falls back to the
    current process executable path.
    """
    env_cmd = os.environ.get(TEAMMATE_COMMAND_ENV_VAR)
    if env_cmd:
        return env_cmd

    # Check if we're running in bundled mode
    try:
        from ...utils.bundled_mode import is_in_bundled_mode  # type: ignore
        if is_in_bundled_mode():
            return sys.executable
    except ImportError:
        pass

    # Fallback: use the script argument
    if len(sys.argv) >= 1:
        return sys.argv[0]
    return sys.executable


def _shell_quote(value: str) -> str:
    """Shell-quote a single value."""
    return shlex.quote(value)


def build_inherited_cli_flags(
    plan_mode_required: bool = False,
    permission_mode: str = "",
) -> str:
    """Build CLI flags to propagate from the current session to spawned teammates.

    This ensures teammates inherit important settings like permission mode,
    model selection, and plugin configuration from their parent.

    Args:
        plan_mode_required: If True, don't inherit bypass permissions.
        permission_mode: Permission mode to propagate.

    Returns:
        Space-joined CLI flags string.
    """
    flags: List[str] = []

    # Propagate permission mode to teammates, but NOT if plan mode is required
    if plan_mode_required:
        # Don't inherit bypass permissions when plan mode is required
        pass
    else:
        try:
            from ...bootstrap.state import (
                get_session_bypass_permissions_mode,
            )
            bypass = get_session_bypass_permissions_mode()
        except ImportError:
            bypass = False

        if permission_mode == "bypassPermissions" or bypass:
            flags.append("--dangerously-skip-permissions")
        elif permission_mode == "acceptEdits":
            flags.append("--permission-mode acceptEdits")

    # Propagate --model if explicitly set via CLI
    try:
        from ...bootstrap.state import get_main_loop_model_override
        model_override = get_main_loop_model_override()
        if model_override:
            flags.append(f"--model {_shell_quote(model_override)}")
    except ImportError:
        pass

    # Propagate --settings if set via CLI
    try:
        from ...bootstrap.state import get_flag_settings_path
        settings_path = get_flag_settings_path()
        if settings_path:
            flags.append(f"--settings {_shell_quote(settings_path)}")
    except ImportError:
        pass

    # Propagate --plugin-dir for each inline plugin
    try:
        from ...bootstrap.state import get_inline_plugins
        inline_plugins = get_inline_plugins()
        for plugin_dir in inline_plugins:
            flags.append(f"--plugin-dir {_shell_quote(plugin_dir)}")
    except ImportError:
        pass

    # Propagate --teammate-mode so tmux teammates use the same mode as leader
    session_mode = get_teammate_mode_from_snapshot()
    flags.append(f"--teammate-mode {session_mode}")

    # Propagate --chrome / --no-chrome if explicitly set on the CLI
    try:
        from ...bootstrap.state import get_chrome_flag_override
        chrome_flag_override = get_chrome_flag_override()
        if chrome_flag_override is True:
            flags.append("--chrome")
        elif chrome_flag_override is False:
            flags.append("--no-chrome")
    except ImportError:
        pass

    return " ".join(flags)


# Environment variables that must be explicitly forwarded to tmux-spawned teammates.
_TEAMMATE_ENV_VARS = [
    # API provider selection
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "CLAUDE_CODE_USE_FOUNDRY",
    # Custom API endpoint
    "ANTHROPIC_BASE_URL",
    # Config directory override
    "CLAUDE_CONFIG_DIR",
    # CCR marker
    "CLAUDE_CODE_REMOTE",
    "CLAUDE_CODE_REMOTE_MEMORY_DIR",
    # Upstream proxy
    "HTTPS_PROXY",
    "https_proxy",
    "HTTP_PROXY",
    "http_proxy",
    "NO_PROXY",
    "no_proxy",
    "SSL_CERT_FILE",
    "NODE_EXTRA_CA_CERTS",
    "REQUESTS_CA_BUNDLE",
    "CURL_CA_BUNDLE",
]


def build_inherited_env_vars() -> str:
    """Build the env KEY=VALUE string for teammate spawn commands.

    Always includes CLAUDECODE=1 and CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1,
    plus any provider/config env vars set in the current process.

    Returns:
        Space-joined env var assignments string.
    """
    env_vars = ["CLAUDECODE=1", "CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1"]

    for key in _TEAMMATE_ENV_VARS:
        value = os.environ.get(key)
        if value is not None and value != "":
            env_vars.append(f"{key}={_shell_quote(value)}")

    return " ".join(env_vars)

"""
Ported from: commands/reload-plugins/reload-plugins.ts

/reload-plugins command — refresh the active plugin set (skills, commands,
agents, hooks, MCP/LSP servers) that are loaded from installed plugin packages.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _is_env_truthy(val: Optional[str]) -> bool:
    return val is not None and val.strip().lower() not in ("", "0", "false", "no")


def _is_remote_mode() -> bool:
    import os
    try:
        from claude_code.bootstrap.state import get_is_remote_mode  # type: ignore[import]
        return get_is_remote_mode()
    except ImportError:
        return _is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE"))


def _plural(count: int, noun: str) -> str:
    """Return ``"{count} {noun}(s)"`` with simple English plural rules."""
    try:
        from claude_code.utils.string_utils import plural  # type: ignore[import]
        return plural(count, noun)
    except ImportError:
        return f"{noun}s" if count != 1 else noun


async def _redownload_user_settings() -> bool:
    try:
        from claude_code.services.settings_sync.index import redownload_user_settings  # type: ignore[import]
        return await redownload_user_settings()
    except ImportError:
        return False


def _notify_settings_change(source: str) -> None:
    try:
        from claude_code.utils.settings.change_detector import settings_change_detector  # type: ignore[import]
        settings_change_detector.notify_change(source)
    except ImportError:
        pass


async def _refresh_active_plugins(set_app_state: Optional[Any]) -> Dict[str, int]:
    try:
        from claude_code.utils.plugins.refresh import refresh_active_plugins  # type: ignore[import]
        return await refresh_active_plugins(set_app_state)
    except ImportError:
        # Stub result — no plugins actually refreshed
        return {
            "enabled_count": 0,
            "command_count": 0,
            "agent_count": 0,
            "hook_count": 0,
            "mcp_count": 0,
            "lsp_count": 0,
            "error_count": 0,
        }


def _feature_enabled(name: str) -> bool:
    try:
        from claude_code.bootstrap.features import feature  # type: ignore[import]
        return feature(name)
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call(
    _args: str = "",
    context: Optional[object] = None,
) -> Dict[str, str]:
    """
    Handle the /reload-plugins command.

    Parameters
    ----------
    _args:
        Unused; the command takes no arguments.
    context:
        ToolUseContext duck-typed object; may expose ``set_app_state``.

    Returns
    -------
    dict
        ``{"type": "text", "value": <summary>}``
    """
    import os

    # Re-pull user settings in remote mode before sweeping the plugin cache
    if (
        _feature_enabled("DOWNLOAD_USER_SETTINGS")
        and (
            _is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE"))
            or _is_remote_mode()
        )
    ):
        applied = await _redownload_user_settings()
        if applied:
            _notify_settings_change("userSettings")

    set_app_state = getattr(context, "set_app_state", None)
    r = await _refresh_active_plugins(set_app_state)

    def n(count: int, noun: str) -> str:
        return f"{count} {_plural(count, noun)}"

    parts = [
        n(r.get("enabled_count", 0), "plugin"),
        n(r.get("command_count", 0), "skill"),
        n(r.get("agent_count", 0), "agent"),
        n(r.get("hook_count", 0), "hook"),
        n(r.get("mcp_count", 0), "plugin MCP server"),
        n(r.get("lsp_count", 0), "plugin LSP server"),
    ]
    msg = "Reloaded: " + " \u00b7 ".join(parts)

    error_count = r.get("error_count", 0)
    if error_count > 0:
        msg += f"\n{n(error_count, 'error')} during load. Run /doctor for details."

    return {"type": "text", "value": msg}

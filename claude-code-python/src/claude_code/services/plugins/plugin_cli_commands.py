"""CLI command wrappers for plugin operations.
Ported from services/plugins/pluginCliCommands.ts.

Provides thin async wrappers around the core plugin operations with
CLI-specific logging and error handling.
"""
from __future__ import annotations
import sys
from typing import Literal, Optional

# Scope types that mirror the TypeScript originals
PluginScope = Literal["user", "project", "local"]
InstallableScope = Literal["user", "project", "local"]

VALID_INSTALLABLE_SCOPES: frozenset = frozenset(["user", "project", "local"])
VALID_UPDATE_SCOPES: frozenset = frozenset(["user", "project", "local"])

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tick() -> str:
    return "✔"


def _cross() -> str:
    return "✖"


def _log(msg: str) -> None:
    print(msg, flush=True)


def _log_error(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _error_message(exc: Exception) -> str:
    return str(exc)


async def _plugin_op(name: str, *args, **kwargs):  # type: ignore[no-untyped-def]
    """Dispatch to the underlying plugin operations module."""
    from claude_code.services.plugins.plugin_operations import (  # type: ignore[import]
        install_plugin_op,
        uninstall_plugin_op,
        enable_plugin_op,
        disable_plugin_op,
        disable_all_plugins_op,
        update_plugin_op,
    )
    ops = {
        "install": install_plugin_op,
        "uninstall": uninstall_plugin_op,
        "enable": enable_plugin_op,
        "disable": disable_plugin_op,
        "disable_all": disable_all_plugins_op,
        "update": update_plugin_op,
    }
    return await ops[name](*args, **kwargs)


def _handle_error(error: Exception, command: str, plugin: Optional[str] = None) -> None:
    op = (
        f'{command} plugin "{plugin}"'
        if plugin
        else ("disable all plugins" if command == "disable-all" else f"{command} plugins")
    )
    _log_error(f"{_cross()} Failed to {op}: {_error_message(error)}")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Public CLI commands
# ---------------------------------------------------------------------------


async def install_plugin(
    plugin: str,
    scope: InstallableScope = "user",
) -> None:
    """Install a plugin non-interactively.

    Args:
        plugin: Plugin name or ``plugin@marketplace`` identifier.
        scope: Installation scope — ``user``, ``project``, or ``local``.
    """
    try:
        result = await _plugin_op("install", plugin, scope)
        if not result.get("success"):
            raise RuntimeError(result.get("message", "Unknown error"))
        _log(f"{_tick()} {result.get('message', 'Plugin installed')}")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        _handle_error(exc, "install", plugin)


async def uninstall_plugin(
    plugin: str,
    scope: InstallableScope = "user",
    keep_data: bool = False,
) -> None:
    """Uninstall a plugin non-interactively.

    Args:
        plugin: Plugin name or ``plugin@marketplace`` identifier.
        scope: Scope to uninstall from.
        keep_data: When True, preserve plugin data files.
    """
    try:
        result = await _plugin_op("uninstall", plugin, scope, not keep_data)
        if not result.get("success"):
            raise RuntimeError(result.get("message", "Unknown error"))
        _log(f"{_tick()} {result.get('message', 'Plugin uninstalled')}")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        _handle_error(exc, "uninstall", plugin)


async def enable_plugin(
    plugin: str,
    scope: Optional[InstallableScope] = None,
) -> None:
    """Enable a plugin non-interactively.

    Args:
        plugin: Plugin name or ``plugin@marketplace`` identifier.
        scope: Optional scope; if omitted the most specific scope is used.
    """
    try:
        result = await _plugin_op("enable", plugin, scope)
        if not result.get("success"):
            raise RuntimeError(result.get("message", "Unknown error"))
        _log(f"{_tick()} {result.get('message', 'Plugin enabled')}")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        _handle_error(exc, "enable", plugin)


async def disable_plugin(
    plugin: str,
    scope: Optional[InstallableScope] = None,
) -> None:
    """Disable a plugin non-interactively.

    Args:
        plugin: Plugin name or ``plugin@marketplace`` identifier.
        scope: Optional scope; if omitted the most specific scope is used.
    """
    try:
        result = await _plugin_op("disable", plugin, scope)
        if not result.get("success"):
            raise RuntimeError(result.get("message", "Unknown error"))
        _log(f"{_tick()} {result.get('message', 'Plugin disabled')}")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        _handle_error(exc, "disable", plugin)


async def disable_all_plugins() -> None:
    """Disable all enabled plugins non-interactively."""
    try:
        result = await _plugin_op("disable_all")
        if not result.get("success"):
            raise RuntimeError(result.get("message", "Unknown error"))
        _log(f"{_tick()} {result.get('message', 'All plugins disabled')}")
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        _handle_error(exc, "disable-all")


async def update_plugin_cli(
    plugin: str,
    scope: PluginScope,
) -> None:
    """Update a plugin non-interactively.

    Args:
        plugin: Plugin name or ``plugin@marketplace`` identifier.
        scope: Scope to update.
    """
    try:
        print(f'Checking for updates for plugin "{plugin}" at {scope} scope…', flush=True)
        result = await _plugin_op("update", plugin, scope)
        if not result.get("success"):
            raise RuntimeError(result.get("message", "Unknown error"))
        print(f"{_tick()} {result.get('message', 'Plugin updated')}", flush=True)
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as exc:
        _handle_error(exc, "update", plugin)

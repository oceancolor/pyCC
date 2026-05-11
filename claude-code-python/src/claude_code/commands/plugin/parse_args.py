"""
Ported from: commands/plugin/parseArgs.ts

Parse /plugin subcommand argument strings into structured command objects.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal, Optional, Union


# ---------------------------------------------------------------------------
# Typed result variants (mirror the TypeScript discriminated union)
# ---------------------------------------------------------------------------

@dataclass
class MenuCommand:
    type: Literal["menu"] = field(default="menu", init=False)


@dataclass
class HelpCommand:
    type: Literal["help"] = field(default="help", init=False)


@dataclass
class InstallCommand:
    type: Literal["install"] = field(default="install", init=False)
    marketplace: Optional[str] = None
    plugin: Optional[str] = None


@dataclass
class ManageCommand:
    type: Literal["manage"] = field(default="manage", init=False)


@dataclass
class UninstallCommand:
    type: Literal["uninstall"] = field(default="uninstall", init=False)
    plugin: Optional[str] = None


@dataclass
class EnableCommand:
    type: Literal["enable"] = field(default="enable", init=False)
    plugin: Optional[str] = None


@dataclass
class DisableCommand:
    type: Literal["disable"] = field(default="disable", init=False)
    plugin: Optional[str] = None


@dataclass
class ValidateCommand:
    type: Literal["validate"] = field(default="validate", init=False)
    path: Optional[str] = None


@dataclass
class MarketplaceCommand:
    type: Literal["marketplace"] = field(default="marketplace", init=False)
    action: Optional[Literal["add", "remove", "update", "list"]] = None
    target: Optional[str] = None


ParsedCommand = Union[
    MenuCommand,
    HelpCommand,
    InstallCommand,
    ManageCommand,
    UninstallCommand,
    EnableCommand,
    DisableCommand,
    ValidateCommand,
    MarketplaceCommand,
]

# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

_URL_PREFIXES = ("http://", "https://", "file://")
_PATH_CHARS = frozenset("/\\")


def parse_plugin_args(args: Optional[str] = None) -> ParsedCommand:
    """
    Parse the raw argument string from the /plugin command.

    Parameters
    ----------
    args:
        The portion of the slash-command after "/plugin", e.g. "install foo"
        or "marketplace add https://example.com".  ``None`` or empty string
        returns :class:`MenuCommand`.

    Returns
    -------
    ParsedCommand
        A typed result object describing the requested action.
    """
    if not args:
        return MenuCommand()

    parts = re.split(r"\s+", args.strip())
    if not parts or not parts[0]:
        return MenuCommand()

    command = parts[0].lower()

    if command in ("help", "--help", "-h"):
        return HelpCommand()

    if command in ("install", "i"):
        target = parts[1] if len(parts) > 1 else None
        if target is None:
            return InstallCommand()

        # plugin@marketplace syntax
        if "@" in target:
            plugin, _, marketplace = target.partition("@")
            return InstallCommand(plugin=plugin, marketplace=marketplace)

        # URL or path → treat as marketplace
        is_marketplace = (
            any(target.startswith(p) for p in _URL_PREFIXES)
            or any(c in target for c in _PATH_CHARS)
        )
        if is_marketplace:
            return InstallCommand(marketplace=target)

        return InstallCommand(plugin=target)

    if command == "manage":
        return ManageCommand()

    if command == "uninstall":
        return UninstallCommand(plugin=parts[1] if len(parts) > 1 else None)

    if command == "enable":
        return EnableCommand(plugin=parts[1] if len(parts) > 1 else None)

    if command == "disable":
        return DisableCommand(plugin=parts[1] if len(parts) > 1 else None)

    if command == "validate":
        target = " ".join(parts[1:]).strip()
        return ValidateCommand(path=target if target else None)

    if command in ("marketplace", "market"):
        action_str = parts[1].lower() if len(parts) > 1 else None
        target = " ".join(parts[2:]) if len(parts) > 2 else None

        if action_str == "add":
            return MarketplaceCommand(action="add", target=target)
        if action_str in ("remove", "rm"):
            return MarketplaceCommand(action="remove", target=target)
        if action_str == "update":
            return MarketplaceCommand(action="update", target=target)
        if action_str == "list":
            return MarketplaceCommand(action="list")
        return MarketplaceCommand()

    # Unknown command — fall back to menu
    return MenuCommand()

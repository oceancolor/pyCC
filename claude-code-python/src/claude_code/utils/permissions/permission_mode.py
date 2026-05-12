"""
Permission modes - defines and manages permission mode types.
"""

from __future__ import annotations

from typing import List, Optional

PERMISSION_MODES: List[str] = [
    "default",
    "plan",
    "acceptEdits",
    "bypassPermissions",
    "dontAsk",
    "auto",
    "bubble",
]

EXTERNAL_PERMISSION_MODES: List[str] = [
    "default",
    "plan",
    "acceptEdits",
    "bypassPermissions",
    "dontAsk",
]

PermissionMode = str
ExternalPermissionMode = str

PAUSE_ICON = "⏸"

_MODE_CONFIG = {
    "default": {"title": "Default", "shortTitle": "Default", "symbol": "", "color": "text", "external": "default"},
    "plan": {"title": "Plan Mode", "shortTitle": "Plan", "symbol": PAUSE_ICON, "color": "planMode", "external": "plan"},
    "acceptEdits": {"title": "Accept edits", "shortTitle": "Accept", "symbol": "⏵⏵", "color": "autoAccept", "external": "acceptEdits"},
    "bypassPermissions": {"title": "Bypass Permissions", "shortTitle": "Bypass", "symbol": "⏵⏵", "color": "error", "external": "bypassPermissions"},
    "dontAsk": {"title": "Don't Ask", "shortTitle": "DontAsk", "symbol": "⏵⏵", "color": "error", "external": "dontAsk"},
    "auto": {"title": "Auto mode", "shortTitle": "Auto", "symbol": "⏵⏵", "color": "warning", "external": "default"},
}


def _get_mode_config(mode: PermissionMode) -> dict:
    return _MODE_CONFIG.get(mode, _MODE_CONFIG["default"])


def is_external_permission_mode(mode: PermissionMode) -> bool:
    """Type guard to check if a PermissionMode is an ExternalPermissionMode."""
    return mode not in ("auto", "bubble")


def to_external_permission_mode(mode: PermissionMode) -> ExternalPermissionMode:
    return _get_mode_config(mode)["external"]


def permission_mode_from_string(s: str) -> PermissionMode:
    return s if s in PERMISSION_MODES else "default"


def permission_mode_title(mode: PermissionMode) -> str:
    return _get_mode_config(mode)["title"]


def is_default_mode(mode: Optional[PermissionMode]) -> bool:
    return mode == "default" or mode is None


def permission_mode_short_title(mode: PermissionMode) -> str:
    return _get_mode_config(mode)["shortTitle"]


def permission_mode_symbol(mode: PermissionMode) -> str:
    return _get_mode_config(mode)["symbol"]


def get_mode_color(mode: PermissionMode) -> str:
    return _get_mode_config(mode)["color"]

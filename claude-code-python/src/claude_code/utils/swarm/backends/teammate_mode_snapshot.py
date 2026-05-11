"""
Teammate mode snapshot module.

Port of utils/swarm/backends/teammateModeSnapshot.ts

Captures the teammate mode at session startup so runtime config changes
don't affect the current session.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

logger = logging.getLogger(__name__)

TeammateMode = Literal["auto", "tmux", "in-process"]

# Module-level variable to hold the captured mode at startup
_initial_teammate_mode: Optional[TeammateMode] = None

# CLI override (set before capture if --teammate-mode is provided)
_cli_teammate_mode_override: Optional[TeammateMode] = None


def set_cli_teammate_mode_override(mode: TeammateMode) -> None:
    """
    Set the CLI override for teammate mode.
    Must be called before capture_teammate_mode_snapshot().
    """
    global _cli_teammate_mode_override
    _cli_teammate_mode_override = mode


def get_cli_teammate_mode_override() -> Optional[TeammateMode]:
    """
    Get the current CLI override, if any.
    Returns None if no CLI override was set.
    """
    return _cli_teammate_mode_override


def clear_cli_teammate_mode_override(new_mode: TeammateMode) -> None:
    """
    Clear the CLI override and update the snapshot to the new mode.
    Called when user changes the setting in the UI, allowing their change to take effect.

    :param new_mode: The new mode the user selected.
    """
    global _cli_teammate_mode_override, _initial_teammate_mode
    _cli_teammate_mode_override = None
    _initial_teammate_mode = new_mode
    logger.debug("[TeammateModeSnapshot] CLI override cleared, new mode: %s", new_mode)


def capture_teammate_mode_snapshot() -> None:
    """
    Capture the teammate mode at session startup.
    Called early in startup, after CLI args are parsed.
    CLI override takes precedence over config.
    """
    global _initial_teammate_mode

    if _cli_teammate_mode_override:
        _initial_teammate_mode = _cli_teammate_mode_override
        logger.debug(
            "[TeammateModeSnapshot] Captured from CLI override: %s",
            _initial_teammate_mode,
        )
    else:
        # Defer import to avoid circular dependency
        try:
            from ...settings.settings import get_initial_settings  # type: ignore[import]

            settings = get_initial_settings()
            _initial_teammate_mode = getattr(settings, "teammate_mode", None) or "auto"
        except Exception:
            _initial_teammate_mode = "auto"

        logger.debug(
            "[TeammateModeSnapshot] Captured from config: %s", _initial_teammate_mode
        )


def get_teammate_mode_from_snapshot() -> TeammateMode:
    """
    Get the teammate mode for this session.
    Returns the snapshot captured at startup, ignoring any runtime config changes.
    """
    global _initial_teammate_mode

    if _initial_teammate_mode is None:
        # Initialization bug — capture should happen in setup
        logger.error(
            "[TeammateModeSnapshot] get_teammate_mode_from_snapshot called before capture "
            "— this indicates an initialization bug"
        )
        capture_teammate_mode_snapshot()

    return _initial_teammate_mode or "auto"

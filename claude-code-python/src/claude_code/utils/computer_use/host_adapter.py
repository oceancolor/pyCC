"""
host_adapter.py - Computer use host adapter for CLI.

Port of TypeScript hostAdapter.ts.
"""

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_cached_adapter: Optional[Any] = None


class DebugLogger:
    """Logger that routes to debug logging."""

    def silly(self, message: str, *args: Any) -> None:
        logger.debug(message, *args)

    def debug(self, message: str, *args: Any) -> None:
        logger.debug(message, *args)

    def info(self, message: str, *args: Any) -> None:
        logger.info(message, *args)

    def warn(self, message: str, *args: Any) -> None:
        logger.warning(message, *args)

    def error(self, message: str, *args: Any) -> None:
        logger.error(message, *args)


class ComputerUseHostAdapter:
    """Host adapter for computer use CLI integration."""

    def __init__(self):
        from .common import COMPUTER_USE_MCP_SERVER_NAME
        self.server_name = COMPUTER_USE_MCP_SERVER_NAME
        self.logger = DebugLogger()
        self._executor = None

    @property
    def executor(self) -> Any:
        if self._executor is None:
            from .executor import create_cli_executor
            from .gates import get_chicago_sub_gates

            def get_mouse_animation():
                return get_chicago_sub_gates().get('mouseAnimation', True)

            def get_hide_before_action():
                return get_chicago_sub_gates().get('hideBeforeAction', True)

            self._executor = create_cli_executor({
                'getMouseAnimationEnabled': get_mouse_animation,
                'getHideBeforeActionEnabled': get_hide_before_action,
            })
        return self._executor

    async def ensure_os_permissions(self) -> dict:
        """Check OS-level permissions for computer use."""
        try:
            from .swift_loader import require_computer_use_swift
            cu = require_computer_use_swift()
            accessibility = cu.tcc.check_accessibility()
            screen_recording = cu.tcc.check_screen_recording()
            if accessibility and screen_recording:
                return {'granted': True}
            return {'granted': False, 'accessibility': accessibility, 'screenRecording': screen_recording}
        except Exception:
            return {'granted': False, 'accessibility': False, 'screenRecording': False}

    def is_disabled(self) -> bool:
        """Check if computer use is disabled."""
        from .gates import get_chicago_enabled
        return not get_chicago_enabled()

    def get_sub_gates(self) -> dict:
        """Get sub-feature gates."""
        from .gates import get_chicago_sub_gates
        return get_chicago_sub_gates()

    def get_auto_unhide_enabled(self) -> bool:
        """Always auto-unhide at turn end."""
        return True

    def crop_raw_patch(self, *args: Any, **kwargs: Any) -> None:
        """Pixel-validation — not supported in CLI (returns None)."""
        return None


def get_computer_use_host_adapter() -> ComputerUseHostAdapter:
    """
    Process-lifetime singleton for the computer use host adapter.

    Returns:
        ComputerUseHostAdapter instance.
    """
    global _cached_adapter
    if _cached_adapter is None:
        _cached_adapter = ComputerUseHostAdapter()
    return _cached_adapter

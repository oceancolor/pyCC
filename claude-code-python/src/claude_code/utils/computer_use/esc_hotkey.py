"""
esc_hotkey.py - Global Escape key hotkey for aborting computer use.

Port of TypeScript escHotkey.ts.
"""

import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_registered = False


def register_esc_hotkey(on_escape: Callable[[], None]) -> bool:
    """
    Register a global Escape key handler.

    On non-macOS platforms, this is a no-op that returns False.

    Args:
        on_escape: Callback to invoke when Escape is pressed.

    Returns:
        True if registered successfully, False otherwise.
    """
    global _registered

    if _registered:
        return True

    try:
        from .swift_loader import require_computer_use_swift
        cu = require_computer_use_swift()
        if not cu.hotkey.register_escape(on_escape):
            logger.warning('[cu-esc] registerEscape returned false')
            return False
        from .drain_run_loop import retain_pump
        retain_pump()
        _registered = True
        logger.debug('[cu-esc] registered')
        return True
    except ImportError:
        # Not on macOS or swift not available
        logger.debug('[cu-esc] swift not available, ESC hotkey not registered')
        return False
    except Exception as err:
        logger.warning(f'[cu-esc] register failed: {err}')
        return False


def unregister_esc_hotkey() -> None:
    """Unregister the global Escape key handler."""
    global _registered

    if not _registered:
        return

    try:
        from .swift_loader import require_computer_use_swift
        require_computer_use_swift().hotkey.unregister()
    except Exception:
        pass
    finally:
        try:
            from .drain_run_loop import release_pump
            release_pump()
        except Exception:
            pass
        _registered = False
        logger.debug('[cu-esc] unregistered')


def notify_expected_escape() -> None:
    """Notify that the next Escape is expected (from model synthesis)."""
    if not _registered:
        return

    try:
        from .swift_loader import require_computer_use_swift
        require_computer_use_swift().hotkey.notify_expected_escape()
    except Exception:
        pass

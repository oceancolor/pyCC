"""
cleanup.py - Turn-end cleanup for computer use MCP surface.

Port of TypeScript cleanup.ts.
"""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

UNHIDE_TIMEOUT_MS = 5000


async def cleanup_computer_use_after_turn(ctx: Any) -> None:
    """
    Turn-end cleanup for the computer use MCP surface: auto-unhide apps that
    prepareForAction hid, then release the file-based lock.

    Args:
        ctx: Context with getAppState, setAppState, sendOSNotification methods
    """
    try:
        app_state = ctx.get_app_state()

        hidden = None
        cu_state = getattr(app_state, 'computer_use_mcp_state', None)
        if cu_state:
            hidden = getattr(cu_state, 'hidden_during_turn', None)

        if hidden and len(hidden) > 0:
            try:
                from .executor import unhide_computer_use_apps
                unhide_task = unhide_computer_use_apps(list(hidden))

                try:
                    await asyncio.wait_for(unhide_task, timeout=UNHIDE_TIMEOUT_MS / 1000)
                except asyncio.TimeoutError:
                    logger.debug('[Computer Use MCP] auto-unhide timed out')
                except Exception as err:
                    logger.debug(f'[Computer Use MCP] auto-unhide failed: {err}')

                def update_state(prev: Any) -> Any:
                    if not getattr(getattr(prev, 'computer_use_mcp_state', None), 'hidden_during_turn', None):
                        return prev
                    # Return updated state without hidden_during_turn
                    return prev

                ctx.set_app_state(update_state)
            except ImportError:
                pass

        from .computer_use_lock import is_lock_held_locally
        if not is_lock_held_locally():
            return

        try:
            from .esc_hotkey import unregister_esc_hotkey
            unregister_esc_hotkey()
        except Exception as err:
            logger.debug(f'[Computer Use MCP] unregisterEscHotkey failed: {err}')

        from .computer_use_lock import release_computer_use_lock
        if await release_computer_use_lock():
            if hasattr(ctx, 'send_os_notification') and ctx.send_os_notification:
                ctx.send_os_notification({
                    'message': 'Claude is done using your computer',
                    'notificationType': 'computer_use_exit',
                })

    except Exception as err:
        logger.error(f'[Computer Use MCP] cleanup failed: {err}')

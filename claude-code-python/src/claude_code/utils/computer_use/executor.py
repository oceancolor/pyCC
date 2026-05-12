"""
executor.py - Computer use executor for CLI.

Port of TypeScript executor.ts (partial - macOS-specific functionality).
"""

import sys
from typing import Any, Dict, List, Optional


async def unhide_computer_use_apps(app_ids: List[str]) -> None:
    """
    Unhide apps that were hidden during a computer use turn.

    Args:
        app_ids: List of app bundle IDs or names to unhide.
    """
    if sys.platform != 'darwin':
        return

    try:
        from .swift_loader import require_computer_use_swift
        from .drain_run_loop import drain_run_loop
        cu = require_computer_use_swift()
        await drain_run_loop(lambda: cu.apps.unhide(app_ids))
    except Exception as err:
        import logging
        logging.getLogger(__name__).debug(f'[executor] unhide failed: {err}')


def create_cli_executor(options: Optional[Dict[str, Any]] = None) -> Any:
    """
    Create a CLI executor for computer use.

    Args:
        options: Options dict with 'getMouseAnimationEnabled' and
                 'getHideBeforeActionEnabled' callables.

    Returns:
        Executor object, or None on non-macOS platforms.
    """
    if sys.platform != 'darwin':
        return None

    try:
        from .swift_loader import require_computer_use_swift
        from .input_loader import require_computer_use_input
        from .common import CLI_HOST_BUNDLE_ID, CLI_CU_CAPABILITIES, get_terminal_bundle_id

        cu = require_computer_use_swift()
        input_api = require_computer_use_input()

        get_mouse_animation = (
            options.get('getMouseAnimationEnabled') if options else None
        ) or (lambda: True)
        get_hide = (
            options.get('getHideBeforeActionEnabled') if options else None
        ) or (lambda: True)

        # Return a simple executor wrapper
        class CliExecutor:
            capabilities = {
                **CLI_CU_CAPABILITIES,
                'hostBundleId': CLI_HOST_BUNDLE_ID,
            }

            async def list_installed_apps(self) -> List[dict]:
                from .drain_run_loop import drain_run_loop
                return await drain_run_loop(lambda: cu.apps.list_installed())

        return CliExecutor()
    except ImportError:
        return None

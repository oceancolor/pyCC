"""
mcp_server.py - Computer use MCP server construction.

Port of TypeScript mcpServer.ts.
"""

import asyncio
import logging
import os
import sys
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

APP_ENUM_TIMEOUT_MS = 1000


async def try_get_installed_app_names() -> Optional[List[str]]:
    """
    Enumerate installed apps, timed. Fails soft.

    Returns:
        List of app names, or None if enumeration failed/timed out.
    """
    import os
    from pathlib import Path
    from .host_adapter import get_computer_use_host_adapter
    from .app_names import filter_apps_for_description

    try:
        adapter = get_computer_use_host_adapter()
        executor = adapter.executor
        if executor is None:
            return None

        try:
            installed = await asyncio.wait_for(
                executor.list_installed_apps(),
                timeout=APP_ENUM_TIMEOUT_MS / 1000,
            )
        except asyncio.TimeoutError:
            logger.debug(
                f'[Computer Use MCP] app enumeration exceeded '
                f'{APP_ENUM_TIMEOUT_MS}ms or failed; tool description omits list'
            )
            return None

        return filter_apps_for_description(installed, str(Path.home()))
    except Exception as err:
        logger.debug(f'[Computer Use MCP] app enumeration failed: {err}')
        return None


def build_computer_use_mcp_server() -> Optional[Any]:
    """
    Construct the in-process computer use MCP server.

    Returns:
        MCP server instance, or None if not available.
    """
    if sys.platform != 'darwin':
        return None

    try:
        from .host_adapter import get_computer_use_host_adapter
        adapter = get_computer_use_host_adapter()
        # In the Python port, we return the adapter which serves as the server proxy
        return adapter
    except Exception as err:
        logger.error(f'[Computer Use MCP] server construction failed: {err}')
        return None

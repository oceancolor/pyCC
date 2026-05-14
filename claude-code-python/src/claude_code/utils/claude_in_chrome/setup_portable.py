"""Portable (non-macOS) claude-in-chrome setup utilities. Ported from utils/claudeInChrome/setupPortable.ts"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import List, Optional

# The browsers we support on all platforms
ChromiumBrowser = str


def get_supported_browsers() -> List[str]:
    """Return the list of Chromium-based browsers we support for native messaging."""
    return ["chrome", "brave", "edge", "opera", "vivaldi", "chromium"]


async def install_native_host_for_all_browsers(
    executable_path: Optional[str] = None,
) -> dict:
    """Install the native messaging host manifest for all detected browsers.

    Args:
        executable_path: Path to the claude binary. Defaults to ``sys.executable``.

    Returns:
        A dict mapping browser name → True (success) or False (failure).
    """
    from .common import detect_installed_browsers
    from .setup import install_native_host_manifest

    installed_browsers = await detect_installed_browsers()
    results: dict = {}

    tasks = {
        browser: install_native_host_manifest(browser, executable_path)
        for browser in installed_browsers
    }

    for browser, task in tasks.items():
        try:
            results[browser] = await task
        except Exception:
            results[browser] = False

    return results


async def uninstall_native_host_for_all_browsers() -> dict:
    """Remove the native messaging host manifest from all known browsers.

    Returns:
        A dict mapping browser name → True (removed/absent) or False (error).
    """
    from .setup import uninstall_native_host_manifest

    results: dict = {}
    for browser in get_supported_browsers():
        try:
            results[browser] = await uninstall_native_host_manifest(browser)
        except Exception:
            results[browser] = False

    return results


def get_extension_install_instructions(browser: str) -> str:
    """Return human-readable instructions for installing the Chrome extension.

    Args:
        browser: The target browser name (e.g. 'chrome', 'brave', 'edge').

    Returns:
        A formatted instruction string.
    """
    store_url = "https://claude.ai/chrome"
    browser_names = {
        "chrome": "Google Chrome",
        "brave": "Brave",
        "edge": "Microsoft Edge",
        "opera": "Opera",
        "vivaldi": "Vivaldi",
        "chromium": "Chromium",
    }
    browser_display = browser_names.get(browser, browser.capitalize())

    return (
        f"To enable Claude in Chrome, install the extension for {browser_display}:\n"
        f"  1. Open {browser_display}\n"
        f"  2. Visit: {store_url}\n"
        f"  3. Click 'Add to Chrome'\n"
        f"  4. Restart Claude Code\n"
    )

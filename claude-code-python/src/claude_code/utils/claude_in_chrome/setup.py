"""Claude-in-Chrome setup utilities. Ported from utils/claudeInChrome/setup.ts"""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Optional

NATIVE_HOST_IDENTIFIER = "com.anthropic.claude_code_browser_extension"
NATIVE_HOST_MANIFEST_NAME = f"{NATIVE_HOST_IDENTIFIER}.json"
CHROME_EXTENSION_RECONNECT_URL = "https://clau.de/chrome/reconnect"


def should_enable_claude_in_chrome(chrome_flag: Optional[bool] = None) -> bool:
    """Determine whether the Claude-in-Chrome feature should be enabled.

    Priority order:
    1. Explicit CLI flag (``--chrome`` / ``--no-chrome``)
    2. ``CLAUDE_CODE_ENABLE_CFC`` environment variable
    3. ``claudeInChromeDefaultEnabled`` in global config
    4. Default: False
    """
    # Non-interactive sessions: off by default unless explicitly requested
    non_interactive = os.environ.get("CLAUDE_CODE_NON_INTERACTIVE") == "1"
    if non_interactive and chrome_flag is not True:
        return False

    if chrome_flag is True:
        return True
    if chrome_flag is False:
        return False

    env_val = os.environ.get("CLAUDE_CODE_ENABLE_CFC", "")
    if env_val.lower() in ("1", "true", "yes"):
        return True
    if env_val.lower() in ("0", "false", "no"):
        return False

    try:
        from claude_code.utils.config import get_global_config

        config = get_global_config()
        val = getattr(config, "claude_in_chrome_default_enabled", None)
        if val is not None:
            return bool(val)
    except Exception:
        pass

    return False


def get_native_messaging_hosts_dir(browser: str = "chrome") -> Optional[str]:
    """Return the native messaging hosts directory for the given browser.

    Returns None for unsupported platforms or unknown browsers.
    """
    from .common import get_native_messaging_path

    return get_native_messaging_path(browser)


def build_native_host_manifest(executable_path: str) -> dict:
    """Build the native messaging host manifest JSON object.

    Args:
        executable_path: Absolute path to the claude binary.

    Returns:
        A dict suitable for serialising to the ``.json`` manifest file.
    """
    return {
        "name": NATIVE_HOST_IDENTIFIER,
        "description": "Claude Code browser extension native messaging host",
        "path": executable_path,
        "type": "stdio",
        "allowed_origins": [
            # Production extension
            "chrome-extension://fcoeoabgfenejglbffodgkkbkcdhcgfn/",
            # Dev extension
            "chrome-extension://dihbgbndebgnbjfmelmegjepbnkhlgni/",
        ],
    }


async def install_native_host_manifest(
    browser: str = "chrome",
    executable_path: Optional[str] = None,
) -> bool:
    """Write the native messaging host manifest for the given browser.

    Args:
        browser: One of the supported Chromium browser names.
        executable_path: Path to the claude binary. Defaults to ``sys.executable``.

    Returns:
        True on success, False on failure.
    """
    import asyncio

    if executable_path is None:
        executable_path = sys.executable

    hosts_dir = get_native_messaging_hosts_dir(browser)
    if not hosts_dir:
        return False

    manifest = build_native_host_manifest(executable_path)
    manifest_path = os.path.join(hosts_dir, NATIVE_HOST_MANIFEST_NAME)

    try:
        loop = asyncio.get_event_loop()

        def _write() -> None:
            os.makedirs(hosts_dir, exist_ok=True)
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, indent=2)
            os.chmod(manifest_path, 0o644)

        await loop.run_in_executor(None, _write)
        return True
    except Exception:
        return False


async def uninstall_native_host_manifest(browser: str = "chrome") -> bool:
    """Remove the native messaging host manifest for the given browser.

    Returns True if removed (or already absent), False on error.
    """
    import asyncio

    hosts_dir = get_native_messaging_hosts_dir(browser)
    if not hosts_dir:
        return False

    manifest_path = os.path.join(hosts_dir, NATIVE_HOST_MANIFEST_NAME)

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: os.unlink(manifest_path))
        return True
    except FileNotFoundError:
        return True
    except Exception:
        return False

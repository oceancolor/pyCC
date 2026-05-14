"""Common utilities for the claude-in-chrome feature. Ported from utils/claudeInChrome/common.ts"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

CLAUDE_IN_CHROME_MCP_SERVER_NAME = "claude-in-chrome"

# Supported Chromium-based browsers
ChromiumBrowser = str  # 'chrome' | 'brave' | 'arc' | 'edge' | 'opera' | 'vivaldi' | 'chromium'

# Configuration for each supported browser
CHROMIUM_BROWSERS: Dict[str, dict] = {
    "chrome": {
        "name": "Google Chrome",
        "macos": {
            "app_name": "Google Chrome",
            "data_path": ["Library", "Application Support", "Google", "Chrome"],
            "native_messaging_path": [
                "Library", "Application Support", "Google", "Chrome", "NativeMessagingHosts"
            ],
        },
        "linux": {
            "binaries": ["google-chrome", "google-chrome-stable"],
            "data_path": [".config", "google-chrome"],
            "native_messaging_path": [".config", "google-chrome", "NativeMessagingHosts"],
        },
        "windows": {
            "data_path": ["Google", "Chrome", "User Data"],
            "registry_key": r"HKCU\Software\Google\Chrome\NativeMessagingHosts",
        },
    },
    "brave": {
        "name": "Brave",
        "macos": {
            "app_name": "Brave Browser",
            "data_path": ["Library", "Application Support", "BraveSoftware", "Brave-Browser"],
            "native_messaging_path": [
                "Library", "Application Support", "BraveSoftware",
                "Brave-Browser", "NativeMessagingHosts"
            ],
        },
        "linux": {
            "binaries": ["brave-browser", "brave"],
            "data_path": [".config", "BraveSoftware", "Brave-Browser"],
            "native_messaging_path": [".config", "BraveSoftware", "Brave-Browser", "NativeMessagingHosts"],
        },
        "windows": {
            "data_path": ["BraveSoftware", "Brave-Browser", "User Data"],
            "registry_key": r"HKCU\Software\BraveSoftware\Brave-Browser\NativeMessagingHosts",
        },
    },
    "edge": {
        "name": "Microsoft Edge",
        "macos": {
            "app_name": "Microsoft Edge",
            "data_path": ["Library", "Application Support", "Microsoft Edge"],
            "native_messaging_path": [
                "Library", "Application Support", "Microsoft Edge", "NativeMessagingHosts"
            ],
        },
        "linux": {
            "binaries": ["microsoft-edge", "microsoft-edge-stable"],
            "data_path": [".config", "microsoft-edge"],
            "native_messaging_path": [".config", "microsoft-edge", "NativeMessagingHosts"],
        },
        "windows": {
            "data_path": ["Microsoft", "Edge", "User Data"],
            "registry_key": r"HKCU\Software\Microsoft\Edge\NativeMessagingHosts",
        },
    },
}


def get_socket_dir() -> str:
    """Return the directory for Unix-domain socket files."""
    return os.path.join(tempfile.gettempdir(), "claude-in-chrome")


def get_secure_socket_path(session_id: str) -> str:
    """Return the path to the Unix-domain socket for the given session."""
    return os.path.join(get_socket_dir(), f"session-{session_id}.sock")


def get_native_messaging_path(browser: str) -> Optional[str]:
    """Return the native messaging hosts directory for the given browser.

    Returns None if the browser is unknown or unsupported on the current platform.
    """
    config = CHROMIUM_BROWSERS.get(browser)
    if config is None:
        return None

    platform = sys.platform
    home = str(Path.home())

    if platform == "darwin":
        parts = config["macos"]["native_messaging_path"]
        return str(Path(home).joinpath(*parts))
    if platform.startswith("linux"):
        parts = config["linux"]["native_messaging_path"]
        return str(Path(home).joinpath(*parts))
    return None


async def detect_installed_browsers() -> List[str]:
    """Return a list of installed Chromium-based browsers."""
    import shutil

    installed: List[str] = []
    platform = sys.platform

    for browser, config in CHROMIUM_BROWSERS.items():
        if platform.startswith("linux"):
            for binary in config["linux"]["binaries"]:
                if shutil.which(binary):
                    installed.append(browser)
                    break
        elif platform == "darwin":
            app_path = os.path.join(
                "/Applications", f"{config['macos']['app_name']}.app"
            )
            if os.path.exists(app_path):
                installed.append(browser)
        elif platform == "win32":
            # On Windows check if the User Data dir exists
            appdata = os.environ.get("LOCALAPPDATA", "")
            data_parts = config["windows"]["data_path"]
            candidate = os.path.join(appdata, *data_parts)
            if os.path.isdir(candidate):
                installed.append(browser)

    return installed

"""
Browser opener - Python port of browser.ts

Provides:
- open_path(path) → bool     : open a file/folder with the system default handler
- open_browser(url) → bool   : open a URL in the system/env browser
  - Validates http/https protocol before opening
  - Respects BROWSER env var on all platforms
"""
from __future__ import annotations

import os
import subprocess
import sys
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _validate_url(url: str) -> None:
    """Raise ValueError if url is not a valid http/https URL."""
    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise ValueError(f"Invalid URL format: {url}") from exc

    if parsed.scheme not in ("http", "https"):
        raise ValueError(
            f"Invalid URL protocol: must use http:// or https://, got {parsed.scheme}:"
        )


def _run(cmd: list[str]) -> bool:
    """Run a command, return True if it exits with code 0."""
    try:
        result = subprocess.run(cmd, capture_output=True)
        return result.returncode == 0
    except (FileNotFoundError, OSError):
        return False


def _platform() -> str:
    return sys.platform  # 'darwin' | 'win32' | 'linux' | …


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def open_path(path: str) -> bool:
    """Open a file or folder using the OS default handler.

    Uses 'open' on macOS, 'explorer' on Windows, 'xdg-open' on Linux.
    """
    platform = _platform()
    try:
        if platform == "win32":
            return _run(["explorer", path])
        cmd = "open" if platform == "darwin" else "xdg-open"
        return _run([cmd, path])
    except Exception:
        return False


def open_browser(url: str) -> bool:
    """Open *url* in the system or BROWSER-env browser.

    Returns True on success, False on any failure (including invalid URL).
    """
    try:
        _validate_url(url)
    except ValueError:
        return False

    browser_env = os.environ.get("BROWSER")
    platform = _platform()

    try:
        if platform == "win32":
            if browser_env:
                return _run([browser_env, f'"{url}"'])
            return _run(["rundll32", "url,OpenURL", url])
        else:
            cmd = browser_env or ("open" if platform == "darwin" else "xdg-open")
            return _run([cmd, url])
    except Exception:
        return False

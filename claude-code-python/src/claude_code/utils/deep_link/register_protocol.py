"""Protocol registration for the claude-cli:// URI scheme. Ported from utils/deepLink/registerProtocol.ts"""

from __future__ import annotations

import asyncio
import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Optional

MACOS_BUNDLE_ID = "com.anthropic.claude-code-url-handler"
_APP_NAME = "Claude Code URL Handler"
_DESKTOP_FILE_NAME = "claude-code-url-handler.desktop"
_MACOS_APP_NAME = "Claude Code URL Handler.app"
DEEP_LINK_PROTOCOL = "claude-cli"


def _get_user_applications_dir() -> Path:
    """Return the user-level applications directory for the current platform."""
    sys_platform = sys.platform
    if sys_platform == "darwin":
        return Path.home() / "Applications"
    # Linux: XDG_DATA_HOME/applications
    xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    return Path(xdg_data) / "applications"


async def register_protocol_handler() -> bool:
    """Register the claude-cli:// URI scheme with the operating system.

    Platform details:
    - macOS: Creates a minimal .app trampoline in ~/Applications.
    - Linux: Creates a .desktop file in $XDG_DATA_HOME/applications.
    - Windows: Writes registry keys under HKCU\\Software\\Classes.

    Returns:
        True on success, False on failure.
    """
    sys_platform = sys.platform
    if sys_platform == "darwin":
        return await _register_macos()
    if sys_platform.startswith("linux"):
        return await _register_linux()
    if sys_platform == "win32":
        return await _register_windows()
    return False


async def _register_macos() -> bool:
    """Create a minimal .app bundle in ~/Applications and register it."""
    app_dir = Path.home() / "Applications" / _MACOS_APP_NAME
    contents = app_dir / "Contents"
    macos_dir = contents / "MacOS"

    try:
        macos_dir.mkdir(parents=True, exist_ok=True)

        # Write the launcher script
        launcher = macos_dir / "launcher"
        launcher.write_text(
            "#!/bin/bash\n"
            f'exec "{sys.executable}" --handle-uri "$@"\n'
        )
        launcher.chmod(0o755)

        # Write the Info.plist
        plist = contents / "Info.plist"
        plist.write_text(
            f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleIdentifier</key>
  <string>{MACOS_BUNDLE_ID}</string>
  <key>CFBundleName</key>
  <string>{_APP_NAME}</string>
  <key>CFBundleExecutable</key>
  <string>launcher</string>
  <key>CFBundleURLTypes</key>
  <array>
    <dict>
      <key>CFBundleURLName</key>
      <string>{MACOS_BUNDLE_ID}</string>
      <key>CFBundleURLSchemes</key>
      <array>
        <string>{DEEP_LINK_PROTOCOL}</string>
      </array>
    </dict>
  </array>
</dict>
</plist>
"""
        )

        # Register with LaunchServices
        proc = await asyncio.create_subprocess_exec(
            "/System/Library/Frameworks/CoreServices.framework/Frameworks/"
            "LaunchServices.framework/Support/lsregister",
            "-f", str(app_dir),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        return True
    except Exception:
        return False


async def _register_linux() -> bool:
    """Create a .desktop file and register it with xdg-mime."""
    xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
    apps_dir = Path(xdg_data) / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    desktop_file = apps_dir / _DESKTOP_FILE_NAME

    try:
        desktop_file.write_text(
            f"[Desktop Entry]\n"
            f"Name={_APP_NAME}\n"
            f"Type=Application\n"
            f"Exec={sys.executable} --handle-uri %u\n"
            f"MimeType=x-scheme-handler/{DEEP_LINK_PROTOCOL};\n"
            f"NoDisplay=true\n"
        )

        proc = await asyncio.create_subprocess_exec(
            "xdg-mime", "default", _DESKTOP_FILE_NAME,
            f"x-scheme-handler/{DEEP_LINK_PROTOCOL}",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.communicate()
        return True
    except Exception:
        return False


async def _register_windows() -> bool:
    """Write registry keys under HKCU\\Software\\Classes\\claude-cli."""
    try:
        import winreg  # type: ignore[import]

        base_key = f"Software\\Classes\\{DEEP_LINK_PROTOCOL}"
        exe_path = sys.executable.replace("\\", "\\\\")

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, base_key) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f"URL:{_APP_NAME}")
            winreg.SetValueEx(key, "URL Protocol", 0, winreg.REG_SZ, "")

        shell_key = f"{base_key}\\shell\\open\\command"
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, shell_key) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, f'"{exe_path}" --handle-uri "%1"')

        return True
    except Exception:
        return False


async def is_protocol_handler_current() -> bool:
    """Check whether the protocol handler registration is up-to-date."""
    sys_platform = sys.platform
    if sys_platform == "darwin":
        app_dir = Path.home() / "Applications" / _MACOS_APP_NAME
        launcher = app_dir / "Contents" / "MacOS" / "launcher"
        return launcher.exists()
    if sys_platform.startswith("linux"):
        xdg_data = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
        return (Path(xdg_data) / "applications" / _DESKTOP_FILE_NAME).exists()
    if sys_platform == "win32":
        try:
            import winreg  # type: ignore[import]

            winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                f"Software\\Classes\\{DEEP_LINK_PROTOCOL}\\shell\\open\\command",
            )
            return True
        except OSError:
            return False
    return False

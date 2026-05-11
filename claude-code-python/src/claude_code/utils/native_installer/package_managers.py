"""
Package manager detection for Claude CLI.

Detects which package manager installed the currently running Claude instance.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import re
import sys
from typing import Literal, Optional

logger = logging.getLogger(__name__)

PackageManager = Literal[
    "homebrew", "winget", "pacman", "deb", "rpm", "apk", "mise", "asdf", "unknown"
]


def get_platform() -> str:
    """Get the current platform string."""
    platform = sys.platform
    if platform == "darwin":
        return "macos"
    elif platform == "win32":
        return "windows"
    elif platform.startswith("linux"):
        # Check for WSL
        try:
            with open("/proc/version", "r") as f:
                if "microsoft" in f.read().lower():
                    return "wsl"
        except Exception:
            pass
        return "linux"
    return "linux"


async def get_os_release() -> Optional[dict]:
    """
    Parse /etc/os-release to extract the distro ID and ID_LIKE fields.
    Returns None if the file is unreadable.
    """
    try:
        loop = asyncio.get_event_loop()
        content = await loop.run_in_executor(None, _read_os_release)
        if content is None:
            return None

        id_match = re.search(r'^ID=["\']?(\S+?)["\']?\s*$', content, re.MULTILINE)
        id_like_match = re.search(r'^ID_LIKE=["\']?(.+?)["\']?\s*$', content, re.MULTILINE)

        return {
            "id": id_match.group(1) if id_match else "",
            "id_like": id_like_match.group(1).split() if id_like_match else [],
        }
    except Exception:
        return None


def _read_os_release() -> Optional[str]:
    """Read /etc/os-release synchronously."""
    try:
        with open("/etc/os-release", "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def _is_distro_family(os_release: dict, families: list[str]) -> bool:
    """Check if the OS is in one of the given distro families."""
    return os_release["id"] in families or any(
        like in families for like in os_release["id_like"]
    )


def detect_mise() -> bool:
    """
    Detect if Claude was installed via mise (polyglot tool version manager).
    mise installs to: ~/.local/share/mise/installs/<tool>/<version>/
    """
    exec_path = sys.executable or (sys.argv[0] if sys.argv else "")
    if re.search(r"[/\\]mise[/\\]installs[/\\]", exec_path, re.IGNORECASE):
        logger.debug("Detected mise installation: %s", exec_path)
        return True
    return False


def detect_asdf() -> bool:
    """
    Detect if Claude was installed via asdf (polyglot tool version manager).
    asdf installs to: ~/.asdf/installs/<tool>/<version>/
    """
    exec_path = sys.executable or (sys.argv[0] if sys.argv else "")
    if re.search(r"[/\\]\.?asdf[/\\]installs[/\\]", exec_path, re.IGNORECASE):
        logger.debug("Detected asdf installation: %s", exec_path)
        return True
    return False


def detect_homebrew() -> bool:
    """
    Detect if Claude was installed via Homebrew.
    We specifically check for Caskroom to distinguish from npm via Homebrew's npm.
    """
    platform = get_platform()
    if platform not in ("macos", "linux", "wsl"):
        return False

    exec_path = sys.executable or (sys.argv[0] if sys.argv else "")
    if "/Caskroom/" in exec_path:
        logger.debug("Detected Homebrew cask installation: %s", exec_path)
        return True
    return False


def detect_winget() -> bool:
    """
    Detect if Claude was installed via winget.
    Winget installs to: %LOCALAPPDATA%\\Microsoft\\WinGet\\Packages
    """
    platform = get_platform()
    if platform != "windows":
        return False

    exec_path = sys.executable or (sys.argv[0] if sys.argv else "")
    winget_patterns = [
        re.compile(r"Microsoft[/\\]WinGet[/\\]Packages", re.IGNORECASE),
        re.compile(r"Microsoft[/\\]WinGet[/\\]Links", re.IGNORECASE),
    ]
    for pattern in winget_patterns:
        if pattern.search(exec_path):
            logger.debug("Detected winget installation: %s", exec_path)
            return True
    return False


@functools.lru_cache(maxsize=1)
def _detect_pacman_cache() -> Optional[bool]:
    """Cache marker for detect_pacman (set after async call)."""
    return None


async def detect_pacman() -> bool:
    """
    Detect if Claude was installed via pacman.
    We gate on the Arch distro family before invoking pacman.
    """
    platform = get_platform()
    if platform != "linux":
        return False

    os_release = await get_os_release()
    if os_release and not _is_distro_family(os_release, ["arch"]):
        return False

    exec_path = sys.executable or (sys.argv[0] if sys.argv else "")

    try:
        proc = await asyncio.create_subprocess_exec(
            "pacman", "-Qo", exec_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0 and stdout:
            logger.debug("Detected pacman installation: %s", stdout.decode().strip())
            return True
    except Exception:
        pass

    return False


async def detect_deb() -> bool:
    """
    Detect if Claude was installed via a .deb package.
    Uses dpkg -S to check if the executable is owned by a dpkg-managed package.
    """
    platform = get_platform()
    if platform != "linux":
        return False

    os_release = await get_os_release()
    if os_release and not _is_distro_family(os_release, ["debian"]):
        return False

    exec_path = sys.executable or (sys.argv[0] if sys.argv else "")

    try:
        proc = await asyncio.create_subprocess_exec(
            "dpkg", "-S", exec_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0 and stdout:
            logger.debug("Detected deb installation: %s", stdout.decode().strip())
            return True
    except Exception:
        pass

    return False


async def detect_rpm() -> bool:
    """
    Detect if Claude was installed via an RPM package.
    Uses rpm -qf to check if the executable is owned by an RPM package.
    """
    platform = get_platform()
    if platform != "linux":
        return False

    os_release = await get_os_release()
    if os_release and not _is_distro_family(os_release, ["fedora", "rhel", "suse"]):
        return False

    exec_path = sys.executable or (sys.argv[0] if sys.argv else "")

    try:
        proc = await asyncio.create_subprocess_exec(
            "rpm", "-qf", exec_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0 and stdout:
            logger.debug("Detected rpm installation: %s", stdout.decode().strip())
            return True
    except Exception:
        pass

    return False


async def detect_apk() -> bool:
    """
    Detect if Claude was installed via Alpine APK.
    Uses 'apk info --who-owns' to check file ownership.
    """
    platform = get_platform()
    if platform != "linux":
        return False

    os_release = await get_os_release()
    if os_release and not _is_distro_family(os_release, ["alpine"]):
        return False

    exec_path = sys.executable or (sys.argv[0] if sys.argv else "")

    try:
        proc = await asyncio.create_subprocess_exec(
            "apk", "info", "--who-owns", exec_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5.0)
        if proc.returncode == 0 and stdout:
            logger.debug("Detected apk installation: %s", stdout.decode().strip())
            return True
    except Exception:
        pass

    return False


# Module-level cache for get_package_manager
_package_manager_cache: Optional[PackageManager] = None


async def get_package_manager() -> PackageManager:
    """
    Detect which package manager installed Claude.
    Returns 'unknown' if no package manager is detected.
    Memoized - only runs detection once per process.
    """
    global _package_manager_cache
    if _package_manager_cache is not None:
        return _package_manager_cache

    if detect_homebrew():
        _package_manager_cache = "homebrew"
        return _package_manager_cache

    if detect_winget():
        _package_manager_cache = "winget"
        return _package_manager_cache

    if detect_mise():
        _package_manager_cache = "mise"
        return _package_manager_cache

    if detect_asdf():
        _package_manager_cache = "asdf"
        return _package_manager_cache

    if await detect_pacman():
        _package_manager_cache = "pacman"
        return _package_manager_cache

    if await detect_apk():
        _package_manager_cache = "apk"
        return _package_manager_cache

    if await detect_deb():
        _package_manager_cache = "deb"
        return _package_manager_cache

    if await detect_rpm():
        _package_manager_cache = "rpm"
        return _package_manager_cache

    _package_manager_cache = "unknown"
    return _package_manager_cache

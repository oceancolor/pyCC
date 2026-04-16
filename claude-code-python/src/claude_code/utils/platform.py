"""Platform detection utilities. Ported from platform.ts."""
from __future__ import annotations

import os
import platform as _platform
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional

PlatformName = Literal["macos", "windows", "wsl", "linux", "unknown"]
SUPPORTED_PLATFORMS: list[PlatformName] = ["macos", "wsl"]

_VCS_MARKERS: list[tuple[str, str]] = [
    (".git", "git"), (".hg", "mercurial"), (".svn", "svn"),
    (".p4config", "perforce"), ("$tf", "tfs"), (".tfvc", "tfs"),
    (".jj", "jujutsu"), (".sl", "sapling"),
]


def _read_proc_version() -> Optional[str]:
    try:
        return Path("/proc/version").read_text(encoding="utf-8")
    except OSError:
        return None


@lru_cache(maxsize=1)
def get_platform() -> PlatformName:
    """Detect the current operating platform."""
    try:
        sys_name = _platform.system()
        if sys_name == "Darwin":
            return "macos"
        if sys_name == "Windows":
            return "windows"
        if sys_name == "Linux":
            pv = _read_proc_version()
            if pv and ("microsoft" in pv.lower() or "wsl" in pv.lower()):
                return "wsl"
            return "linux"
        return "unknown"
    except Exception:
        return "unknown"


def is_macos() -> bool:
    """Return True when running on macOS."""
    return get_platform() == "macos"


def is_windows() -> bool:
    """Return True when running on Windows."""
    return get_platform() == "windows"


def is_linux() -> bool:
    """Return True when running on native Linux (not WSL)."""
    return get_platform() == "linux"


def is_wsl() -> bool:
    """Return True when running inside WSL."""
    return get_platform() == "wsl"


@lru_cache(maxsize=1)
def get_wsl_version() -> Optional[str]:
    """Return the WSL version string ('1', '2', …) or None if not WSL."""
    if _platform.system() != "Linux":
        return None
    try:
        pv = _read_proc_version()
        if not pv:
            return None
        match = re.search(r"WSL(\d+)", pv, re.IGNORECASE)
        if match:
            return match.group(1)
        if "microsoft" in pv.lower():
            return "1"
    except Exception:
        pass
    return None


def get_linux_distro_info() -> Optional[dict[str, Any]]:
    """Return Linux distro info from /etc/os-release. None on non-Linux."""
    if _platform.system() != "Linux":
        return None
    result: dict[str, Any] = {"linux_kernel": _platform.release()}
    try:
        content = Path("/etc/os-release").read_text(encoding="utf-8")
        for line in content.splitlines():
            m = re.match(r'^(ID|VERSION_ID)=(.*)$', line)
            if m:
                val = m.group(2).strip('"')
                result["linux_distro_id" if m.group(1) == "ID" else "linux_distro_version"] = val
    except OSError:
        pass
    return result


def detect_vcs(directory: Optional[str] = None) -> list[str]:
    """Detect VCS markers in the given directory (defaults to cwd)."""
    detected: set[str] = set()
    if os.environ.get("P4PORT"):
        detected.add("perforce")
    try:
        target = Path(directory) if directory else Path.cwd()
        entries = {p.name for p in target.iterdir()}
        for marker, vcs in _VCS_MARKERS:
            if marker in entries:
                detected.add(vcs)
    except OSError:
        pass
    return sorted(detected)


def get_platform_info() -> dict[str, Any]:
    """Return a dict with all relevant platform information."""
    plat = get_platform()
    info: dict[str, Any] = {
        "platform": plat,
        "is_macos": plat == "macos",
        "is_windows": plat == "windows",
        "is_linux": plat == "linux",
        "is_wsl": plat == "wsl",
        "python_platform": _platform.platform(),
        "machine": _platform.machine(),
        "processor": _platform.processor(),
    }
    if plat == "wsl":
        info["wsl_version"] = get_wsl_version()
    if plat in ("linux", "wsl"):
        info["distro"] = get_linux_distro_info()
    return info

"""IDE path conversion utilities.

Ported from idePathConversion.ts — handles path conversion between
Claude's environment and the IDE's environment (e.g. Windows IDE + WSL).
"""

import re
import subprocess
from abc import ABC, abstractmethod


class IDEPathConverter(ABC):
    """Abstract base for IDE ↔ local path converters."""

    @abstractmethod
    def to_local_path(self, ide_path: str) -> str:
        """Convert path from IDE format to Claude's local format."""

    @abstractmethod
    def to_ide_path(self, local_path: str) -> str:
        """Convert path from Claude's local format to IDE format."""


# Pattern for WSL UNC paths: \\wsl.localhost\<distro>\... or \\wsl$\<distro>\...
_WSL_UNC_RE = re.compile(r'^\\\\wsl(?:\.localhost|\$)\\([^\\]+)(.*)', re.IGNORECASE)


class WindowsToWSLConverter(IDEPathConverter):
    """Converter for Windows IDE + WSL Claude scenario."""

    def __init__(self, wsl_distro_name: str | None = None) -> None:
        self._distro = wsl_distro_name

    def to_local_path(self, windows_path: str) -> str:
        """Convert a Windows path to the WSL local path."""
        if not windows_path:
            return windows_path

        # Check if this path belongs to a different WSL distro
        if self._distro:
            m = _WSL_UNC_RE.match(windows_path)
            if m and m.group(1) != self._distro:
                return windows_path  # Different distro — wslpath would fail

        try:
            result = subprocess.run(
                ['wslpath', '-u', windows_path],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Manual fallback
            path = windows_path.replace('\\', '/')
            path = re.sub(r'^([A-Za-z]):', lambda m: f'/mnt/{m.group(1).lower()}', path)
            return path

    def to_ide_path(self, wsl_path: str) -> str:
        """Convert a WSL path to a Windows path."""
        if not wsl_path:
            return wsl_path
        try:
            result = subprocess.run(
                ['wslpath', '-w', wsl_path],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return wsl_path


def check_wsl_distro_match(windows_path: str, wsl_distro_name: str) -> bool:
    """Return True if the WSL UNC path belongs to *wsl_distro_name*, or if the
    path is not a WSL UNC path at all."""
    m = _WSL_UNC_RE.match(windows_path)
    if m:
        return m.group(1) == wsl_distro_name
    return True  # Not a WSL UNC path → no mismatch

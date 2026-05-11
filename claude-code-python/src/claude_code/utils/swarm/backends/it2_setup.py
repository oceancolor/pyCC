"""
it2 setup utilities: detect and install the it2 CLI for iTerm2 integration.

Port of utils/swarm/backends/it2Setup.ts
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

PythonPackageManager = Literal["uvx", "pipx", "pip"]


class It2InstallResult:
    """Result of attempting to install it2."""

    def __init__(
        self,
        success: bool,
        error: Optional[str] = None,
        package_manager: Optional[PythonPackageManager] = None,
    ) -> None:
        self.success = success
        self.error = error
        self.package_manager = package_manager


class It2VerifyResult:
    """Result of verifying it2 setup."""

    def __init__(
        self,
        success: bool,
        error: Optional[str] = None,
        needs_python_api_enabled: Optional[bool] = None,
    ) -> None:
        self.success = success
        self.error = error
        self.needs_python_api_enabled = needs_python_api_enabled


# ---------------------------------------------------------------------------
# Config key for preference
# ---------------------------------------------------------------------------

_PREFER_TMUX_KEY = "preferTmuxOverIterm2"


def get_prefer_tmux_over_iterm2() -> bool:
    """
    Reads the user's preference for tmux over iTerm2 from global config.
    Returns False if not set (default: use iTerm2 when available).
    """
    try:
        from ....utils.config import get_global_config  # type: ignore[import]

        config = get_global_config()
        return bool(getattr(config, "prefer_tmux_over_iterm2", False))
    except Exception:
        return False


def set_prefer_tmux_over_iterm2(value: bool) -> None:
    """Saves the user's preference for tmux over iTerm2 to global config."""
    try:
        from ....utils.config import get_global_config, save_global_config  # type: ignore[import]

        config = get_global_config()
        config.prefer_tmux_over_iterm2 = value
        save_global_config(config)
    except Exception as e:
        logger.debug("[it2Setup] Failed to save prefer_tmux preference: %s", e)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------


async def _exec_file_no_throw(cmd: str, args: list[str]) -> tuple[str, str, int]:
    """Run a subprocess and return (stdout, stderr, returncode). Never raises."""
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        return (
            stdout_b.decode(errors="replace"),
            stderr_b.decode(errors="replace"),
            proc.returncode or 0,
        )
    except Exception:
        return ("", "", 1)


async def _exec_with_cwd(
    cmd: str, args: list[str], cwd: str
) -> tuple[str, str, int]:
    """Run a subprocess in a specific working directory."""
    try:
        proc = await asyncio.create_subprocess_exec(
            cmd,
            *args,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout_b, stderr_b = await proc.communicate()
        return (
            stdout_b.decode(errors="replace"),
            stderr_b.decode(errors="replace"),
            proc.returncode or 0,
        )
    except Exception:
        return ("", "", 1)


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------


async def detect_python_package_manager() -> Optional[PythonPackageManager]:
    """
    Detects which Python package manager is available on the system.
    Checks in order of preference: uvx (via uv), pipx, pip.

    Returns the detected package manager, or None if none found.
    """
    # Check uv first (preferred for isolated environments)
    uv_result = await _exec_file_no_throw("which", ["uv"])
    if uv_result[2] == 0:
        logger.debug("[it2Setup] Found uv (will use uv tool install)")
        return "uvx"

    # Check pipx
    pipx_result = await _exec_file_no_throw("which", ["pipx"])
    if pipx_result[2] == 0:
        logger.debug("[it2Setup] Found pipx package manager")
        return "pipx"

    # Check pip
    pip_result = await _exec_file_no_throw("which", ["pip"])
    if pip_result[2] == 0:
        logger.debug("[it2Setup] Found pip package manager")
        return "pip"

    # Also check pip3
    pip3_result = await _exec_file_no_throw("which", ["pip3"])
    if pip3_result[2] == 0:
        logger.debug("[it2Setup] Found pip3 package manager")
        return "pip"

    logger.debug("[it2Setup] No Python package manager found")
    return None


async def is_it2_cli_available() -> bool:
    """
    Checks if the it2 CLI tool is installed and accessible.
    Returns True if it2 is available.
    """
    result = await _exec_file_no_throw("which", ["it2"])
    return result[2] == 0


# ---------------------------------------------------------------------------
# Installation
# ---------------------------------------------------------------------------


async def install_it2(
    package_manager: Optional[PythonPackageManager] = None,
) -> It2InstallResult:
    """
    Attempts to install the it2 CLI using the detected (or provided) package manager.

    :param package_manager: Override the detected package manager. If None, auto-detects.
    :returns: It2InstallResult with success status.
    """
    if package_manager is None:
        package_manager = await detect_python_package_manager()

    if package_manager is None:
        return It2InstallResult(
            success=False,
            error=(
                "No Python package manager found. "
                "Install pip, pipx, or uv first, then run: pip install it2"
            ),
        )

    logger.debug("[it2Setup] Installing it2 using %s", package_manager)

    if package_manager == "uvx":
        stdout, stderr, code = await _exec_file_no_throw(
            "uv", ["tool", "install", "it2"]
        )
    elif package_manager == "pipx":
        stdout, stderr, code = await _exec_file_no_throw("pipx", ["install", "it2"])
    else:
        # pip
        stdout, stderr, code = await _exec_file_no_throw(
            "pip", ["install", "--user", "it2"]
        )

    if code == 0:
        logger.debug("[it2Setup] it2 installed successfully via %s", package_manager)
        return It2InstallResult(success=True, package_manager=package_manager)
    else:
        error_msg = stderr.strip() or f"Installation failed with exit code {code}"
        logger.debug("[it2Setup] it2 installation failed: %s", error_msg)
        return It2InstallResult(
            success=False,
            error=error_msg,
            package_manager=package_manager,
        )


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


async def verify_it2_setup() -> It2VerifyResult:
    """
    Verifies that it2 is installed and the iTerm2 Python API is accessible.

    Checks:
    1. it2 command is available
    2. `it2 session list` succeeds (confirms Python API is enabled in iTerm2)
    """
    # Check if it2 is installed
    which_result = await _exec_file_no_throw("which", ["it2"])
    if which_result[2] != 0:
        return It2VerifyResult(success=False, error="it2 CLI not found in PATH.")

    # Check if Python API is accessible
    list_result = await _exec_file_no_throw("it2", ["session", "list"])
    if list_result[2] != 0:
        return It2VerifyResult(
            success=False,
            error=(
                "it2 CLI found but cannot reach the iTerm2 Python API. "
                "Enable it in iTerm2 → Preferences → General → Magic → "
                "'Enable Python API'."
            ),
            needs_python_api_enabled=True,
        )

    return It2VerifyResult(success=True)


# ---------------------------------------------------------------------------
# Setup instructions
# ---------------------------------------------------------------------------


def get_it2_setup_instructions() -> str:
    """Returns instructions for setting up it2 CLI."""
    return (
        "To use iTerm2 native panes with Claude's swarm mode:\n\n"
        "1. Install the it2 CLI:\n"
        "   pip install it2\n"
        "   (or: pipx install it2  /  uv tool install it2)\n\n"
        "2. Enable iTerm2 Python API:\n"
        "   iTerm2 → Preferences → General → Magic → 'Enable Python API'\n\n"
        "3. Restart Claude after setup."
    )

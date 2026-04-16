"""
Local installation detection and management utilities.
Port of localInstaller.ts — detect/install Claude CLI in ~/.claude/local/.
"""
from __future__ import annotations

import asyncio, logging, os, shutil, subprocess, sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Path helpers (lazy — never evaluated at module import time)
# ---------------------------------------------------------------------------

def _get_claude_config_home() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) if env else Path.home() / ".claude"

def get_local_install_dir() -> Path:
    return _get_claude_config_home() / "local"

def get_local_claude_path() -> Path:
    return get_local_install_dir() / "claude"

# ---------------------------------------------------------------------------
# Runtime detection
# ---------------------------------------------------------------------------

def is_running_from_local_installation() -> bool:
    """Return *True* when argv[0] is inside ~/.claude/local/."""
    return "/.claude/local/" in (sys.argv[0] if sys.argv else "")

def get_shell_type() -> str:
    """Return the current user's shell family name."""
    shell = os.environ.get("SHELL", "")
    for name in ("zsh", "bash", "fish"):
        if name in shell:
            return name
    return "unknown"

# ---------------------------------------------------------------------------
# Install info
# ---------------------------------------------------------------------------

@dataclass
class InstallInfo:
    version: Optional[str] = None
    install_path: Optional[Path] = None
    is_local_install: bool = False
    update_available: bool = False
    shell_type: str = field(default_factory=get_shell_type)


def get_install_info() -> InstallInfo:
    """Return information about the current Claude CLI installation."""
    info = InstallInfo(
        is_local_install=is_running_from_local_installation(),
        shell_type=get_shell_type(),
    )
    local = get_local_claude_path()
    if local.exists():
        info.install_path = local
    else:
        found = shutil.which("claude")
        if found:
            info.install_path = Path(found)
    if info.install_path:
        try:
            r = subprocess.run(
                [str(info.install_path), "--version"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                info.version = r.stdout.strip()
        except Exception:
            pass
    return info

# ---------------------------------------------------------------------------
# Filesystem helpers
# ---------------------------------------------------------------------------

def _write_if_missing(path: Path, content: str, mode: Optional[int] = None) -> bool:
    """Atomically create *path* with *content*; return False if already exists."""
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode or 0o644)
        with os.fdopen(fd, "w") as fh:
            fh.write(content)
        return True
    except FileExistsError:
        return False


def ensure_local_package_environment() -> bool:
    """Create the local install dir, package.json, and wrapper script."""
    try:
        local_dir = get_local_install_dir()
        local_dir.mkdir(parents=True, exist_ok=True)
        _write_if_missing(
            local_dir / "package.json",
            '{\n  "name": "claude-local",\n  "version": "0.0.1",\n  "private": true\n}\n',
        )
        wrapper = get_local_claude_path()
        node_bin = local_dir / "node_modules" / ".bin" / "claude"
        created = _write_if_missing(wrapper, f'#!/bin/sh\nexec "{node_bin}" "$@"\n', 0o755)
        if created:
            os.chmod(wrapper, 0o755)
        return True
    except Exception as exc:
        logger.error("Failed to set up local package environment: %s", exc)
        return False

# ---------------------------------------------------------------------------
# Installation helpers
# ---------------------------------------------------------------------------

InstallResult = Literal["in_progress", "success", "install_failed"]


def install_or_update_claude_package(
    channel: str = "latest",
    specific_version: Optional[str] = None,
) -> InstallResult:
    """Install or update the Claude CLI package in the local directory."""
    if not ensure_local_package_environment():
        return "install_failed"
    ver = specific_version or ("stable" if channel == "stable" else "latest")
    try:
        r = subprocess.run(
            ["npm", "install", f"@anthropic-ai/claude-code@{ver}"],
            cwd=get_local_install_dir(), capture_output=True, text=True, timeout=120,
        )
        if r.returncode != 0:
            logger.error("npm install failed: %s", r.stderr)
            return "in_progress" if r.returncode == 190 else "install_failed"
        return "success"
    except Exception as exc:
        logger.error("install_or_update_claude_package error: %s", exc)
        return "install_failed"


def local_installation_exists() -> bool:
    """Return *True* when the managed local installation binary exists."""
    return (get_local_install_dir() / "node_modules" / ".bin" / "claude").exists()


async def check_for_updates() -> bool:
    """Async stub: returns False (update check not yet implemented)."""
    await asyncio.sleep(0)
    return False

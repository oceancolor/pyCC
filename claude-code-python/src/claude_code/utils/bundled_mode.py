"""Bundled mode detection. Ported from bundledMode.ts.

Detects whether Claude Code is running from a bundled/compiled binary (e.g.,
PyInstaller, Nuitka, cx_Freeze) vs directly from source.  Used to resolve
asset paths and adjust behaviour for packaged releases.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

__all__ = [
    "is_bundled_mode",
    "is_dev_mode",
    "get_bundle_dir",
    "get_asset_path",
    "get_app_root",
]


def is_bundled_mode() -> bool:
    """Return True if running from a compiled/bundled binary.

    Detection heuristics (in order of precedence):
    1. ``sys.frozen`` attribute is set – standard PyInstaller flag.
    2. ``CLAUDE_BUNDLED=1`` environment variable is set explicitly.
    """
    if getattr(sys, "frozen", False):
        return True
    return os.environ.get("CLAUDE_BUNDLED", "").lower() in ("1", "true", "yes")


def is_dev_mode() -> bool:
    """Return True if running in development mode (not bundled, dev flag set)."""
    return not is_bundled_mode() and os.environ.get("CLAUDE_DEV", "").lower() in (
        "1",
        "true",
        "yes",
    )


def get_bundle_dir() -> str:
    """Return the directory containing the bundled executable or source root.

    - Bundled: directory of ``sys.executable``
    - Source: directory of this file (``utils/bundled_mode.py``), walking up
      to the package root.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    # Walk up from this file to src/claude_code/utils/ → src/claude_code/ → src/ → root
    return str(Path(__file__).resolve().parents[3])


def get_asset_path(*parts: str) -> str:
    """Return the absolute path to a bundled asset.

    Joins *parts* relative to the bundle/source directory.
    """
    return os.path.join(get_bundle_dir(), *parts)


def get_app_root() -> Optional[str]:
    """Return the application root directory, or None if it cannot be determined."""
    bundle_dir = get_bundle_dir()
    if bundle_dir and os.path.isdir(bundle_dir):
        return bundle_dir
    return None

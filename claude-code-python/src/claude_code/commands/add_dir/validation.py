"""Add-dir validation. Ported from commands/add-dir/validation.ts (110L)."""
from __future__ import annotations
import os
from typing import Optional


def validate_add_dir(path: str) -> Optional[str]:
    """Return error message or None if valid."""
    if not path:
        return "Path is required."
    if not os.path.isabs(path):
        return f"Path must be absolute: {path}"
    if not os.path.isdir(path):
        return f"Directory does not exist: {path}"
    return None

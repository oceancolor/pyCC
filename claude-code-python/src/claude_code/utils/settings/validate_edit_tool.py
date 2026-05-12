"""
Validate edit tool - validates the edit tool's path and permission settings.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple


def validate_edit_tool_path(
    file_path: str,
    cwd: Optional[str] = None,
    allowed_paths: Optional[List[str]] = None,
) -> Tuple[bool, Optional[str]]:
    """
    Validate that a file path is safe for the edit tool.
    Returns (is_valid, error_message).
    """
    if not file_path:
        return False, "File path is required"

    abs_path = os.path.abspath(file_path)

    # Check for directory traversal
    if ".." in file_path.split(os.sep):
        return False, "File path cannot contain directory traversal (..)."

    # Check against allowed paths if specified
    if allowed_paths:
        from ..permissions.path_validation import validate_path_access
        if not validate_path_access(abs_path, allowed_paths, cwd):
            return False, f"File path {abs_path} is not within allowed paths"

    return True, None


def validate_edit_tool_input(input_data: Dict[str, Any]) -> List[str]:
    """Validate edit tool input. Returns list of error messages."""
    errors = []

    file_path = input_data.get("file_path") or input_data.get("filePath")
    if not file_path:
        errors.append("file_path is required")
    elif not isinstance(file_path, str):
        errors.append("file_path must be a string")

    old_string = input_data.get("old_string") or input_data.get("oldString")
    new_string = input_data.get("new_string") or input_data.get("newString")

    if old_string is not None and not isinstance(old_string, str):
        errors.append("old_string must be a string")
    if new_string is not None and not isinstance(new_string, str):
        errors.append("new_string must be a string")

    return errors

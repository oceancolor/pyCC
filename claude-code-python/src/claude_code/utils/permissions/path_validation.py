"""
Path validation - validates file paths against permission rules.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple


def normalize_path(path: str) -> str:
    """Normalize a path for comparison."""
    return os.path.normpath(os.path.expanduser(path))


def is_path_within_directory(path: str, directory: str) -> bool:
    """Check if a path is within a given directory."""
    try:
        norm_path = os.path.realpath(os.path.abspath(path))
        norm_dir = os.path.realpath(os.path.abspath(directory))
        return norm_path.startswith(norm_dir + os.sep) or norm_path == norm_dir
    except Exception:
        return False


def glob_matches_path(pattern: str, path: str) -> bool:
    """Check if a glob pattern matches a path."""
    import fnmatch
    # Normalize separators
    pattern = pattern.replace("\\", "/")
    path = path.replace("\\", "/")
    return fnmatch.fnmatch(path, pattern)


def validate_path_access(
    path: str,
    allowed_paths: Optional[List[str]] = None,
    cwd: Optional[str] = None,
) -> bool:
    """Validate that a path access is permitted."""
    if allowed_paths is None:
        return True

    abs_path = os.path.abspath(path)

    for allowed in allowed_paths:
        allowed_expanded = os.path.expanduser(allowed)
        # Handle glob patterns
        if "*" in allowed_expanded or "?" in allowed_expanded:
            if glob_matches_path(allowed_expanded, abs_path):
                return True
        else:
            allowed_abs = os.path.abspath(allowed_expanded)
            if is_path_within_directory(abs_path, allowed_abs):
                return True

    return False


def check_path_permission(
    path: str,
    rules: List[Dict[str, Any]],
    cwd: Optional[str] = None,
) -> Optional[str]:
    """
    Check path against permission rules.
    Returns 'allow', 'deny', or None if no rule matches.
    """
    abs_path = os.path.abspath(path)

    for rule in rules:
        rule_content = rule.get("ruleContent", "")
        if not rule_content:
            continue

        rule_path = os.path.abspath(os.path.expanduser(rule_content))
        if is_path_within_directory(abs_path, rule_path):
            return rule.get("behavior", "allow")

    return None

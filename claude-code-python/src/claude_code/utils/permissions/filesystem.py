"""
Filesystem permission utilities for Claude Code.
Python port of utils/permissions/filesystem.ts

Provides path validation, permission checking, and working-directory
boundary enforcement for file read/write operations.
"""

from __future__ import annotations

import os
import re
import sys
from os.path import (
    abspath,
    basename,
    dirname,
    expanduser,
    isabs,
    join,
    normpath,
    realpath,
    relpath,
    sep,
)
from pathlib import PurePosixPath
from typing import Any, Dict, List, Optional, Set, Tuple, Union

# ---------------------------------------------------------------------------
# Dangerous files / directories constants
# ---------------------------------------------------------------------------

DANGEROUS_FILES: Tuple[str, ...] = (
    ".gitconfig",
    ".gitmodules",
    ".bashrc",
    ".bash_profile",
    ".zshrc",
    ".zprofile",
    ".profile",
    ".ripgreprc",
    ".mcp.json",
    ".claude.json",
)

DANGEROUS_DIRECTORIES: Tuple[str, ...] = (
    ".git",
    ".vscode",
    ".idea",
    ".claude",
)


# ---------------------------------------------------------------------------
# Platform helpers
# ---------------------------------------------------------------------------

def _get_platform() -> str:
    """Return a platform string: 'windows', 'wsl', 'linux', or 'macos'."""
    if sys.platform.startswith("win"):
        return "windows"
    # Rough WSL detection
    if "microsoft" in (os.uname().release.lower() if hasattr(os, "uname") else ""):
        return "wsl"
    if sys.platform == "darwin":
        return "macos"
    return "linux"


_PLATFORM = _get_platform()


# ---------------------------------------------------------------------------
# Path normalization utilities
# ---------------------------------------------------------------------------

def normalize_case_for_comparison(path: str) -> str:
    """
    Normalize a path for case-insensitive comparison.
    Prevents bypass via mixed-case paths on case-insensitive filesystems.
    Always normalizes to lowercase for consistent security.
    """
    return path.lower()


def expand_home_dir(path: str) -> str:
    """
    Expand ~ to the user's home directory.
    Python equivalent of the TS expandPath / homedir expansion.
    """
    return expanduser(path)


def expand_path(path: str) -> str:
    """
    Expand ~ and make the path absolute.
    Mirrors the TS expandPath helper used throughout filesystem.ts.
    """
    expanded = expanduser(path)
    if not isabs(expanded):
        expanded = join(os.getcwd(), expanded)
    return expanded


def normalize_path_for_permission(path: str) -> str:
    """
    Normalize a path for permission matching:
    1. Expand ~ (home directory)
    2. Make absolute
    3. Normalize path separators and remove redundant components (normpath)

    This is the primary normalization step used before permission checks.
    """
    return normpath(expand_path(path))


def relative_path(from_path: str, to_path: str) -> str:
    """
    Cross-platform relative path calculation that returns POSIX-style paths.
    Mirrors the TS relativePath helper.
    """
    try:
        return relpath(to_path, from_path).replace("\\", "/")
    except ValueError:
        # On Windows, relpath can fail across drives
        return to_path


def to_posix_path(path: str) -> str:
    """Convert a path to POSIX format (forward slashes)."""
    return path.replace("\\", "/")


# ---------------------------------------------------------------------------
# Suspicious Windows path pattern detection
# ---------------------------------------------------------------------------

def has_suspicious_windows_path_pattern(path: str) -> bool:
    """
    Detect suspicious Windows path patterns that could bypass security checks.
    Checks for:
    - NTFS Alternate Data Streams (Windows/WSL only)
    - 8.3 short names (e.g. GIT~1)
    - Long path prefixes (\\?\, \\.\, //?/, //./))
    - Trailing dots and spaces
    - DOS device names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
    - Three or more consecutive dots as path component
    - UNC paths
    """
    # NTFS Alternate Data Streams — Windows/WSL only
    if _PLATFORM in ("windows", "wsl"):
        colon_idx = path.find(":", 2)
        if colon_idx != -1:
            return True

    # 8.3 short names (e.g. GIT~1, CLAUDE~1)
    if re.search(r"~\d", path):
        return True

    # Long path prefixes
    if (
        path.startswith("\\\\?\\")
        or path.startswith("\\\\.\\")
        or path.startswith("//?/")
        or path.startswith("//./")
    ):
        return True

    # Trailing dots and spaces
    if re.search(r"[.\s]+$", path):
        return True

    # DOS device names
    if re.search(r"\.(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])$", path, re.IGNORECASE):
        return True

    # Three or more consecutive dots as path component
    if re.search(r"(^|/|\\)\.{3,}(/|\\|$)", path):
        return True

    # UNC paths (defense-in-depth)
    if contains_vulnerable_unc_path(path):
        return True

    return False


def contains_vulnerable_unc_path(path: str) -> bool:
    """
    Check for UNC-style paths that could access network resources.
    Mirrors the TS containsVulnerableUncPath helper.
    """
    # Check for \\server\share or //server/share patterns
    if path.startswith("\\\\") or path.startswith("//"):
        # Exclude //?/ and //./ (already handled above, but belt-and-suspenders)
        if path.startswith("//?/") or path.startswith("//."):
            return False
        return True
    return False


def contains_path_traversal(relative: str) -> bool:
    """
    Returns True if the relative path contains '..' traversal components.
    Mirrors the TS containsPathTraversal helper.
    """
    parts = relative.replace("\\", "/").split("/")
    return ".." in parts


# ---------------------------------------------------------------------------
# Allowed directories / config path helpers
# ---------------------------------------------------------------------------

def is_path_within_allowed_directories(
    path: str,
    allowed_dirs: List[str],
) -> bool:
    """
    Check whether `path` is within any of the `allowed_dirs`.

    Both path and each allowed_dir are expanded and normalized before
    comparison. Returns True if path equals or is nested under any
    allowed directory.
    """
    norm_path = normalize_path_for_permission(path)
    norm_path_lower = normalize_case_for_comparison(norm_path)

    for allowed in allowed_dirs:
        norm_allowed = normalize_path_for_permission(allowed)
        norm_allowed_lower = normalize_case_for_comparison(norm_allowed)

        # Exact match
        if norm_path_lower == norm_allowed_lower:
            return True

        # Path is nested under allowed dir
        prefix = norm_allowed_lower + sep
        if norm_path_lower.startswith(prefix):
            return True

    return False


def get_allowed_directories(config: Dict[str, Any]) -> List[str]:
    """
    Extract the list of allowed directories from a settings/config dict.
    Looks at permissions.additionalDirectories and the cwd.

    Returns a list of absolute, normalized directory paths.
    """
    directories: List[str] = []

    # Always include cwd
    cwd = os.getcwd()
    directories.append(normpath(cwd))

    # Add permissions.additionalDirectories if present
    permissions = config.get("permissions", {}) or {}
    additional = permissions.get("additionalDirectories", []) or []
    for d in additional:
        expanded = expand_path(d)
        directories.append(normpath(expanded))

    return directories


def check_file_permission(
    path: str,
    operation: str,  # "read" | "write" | "create"
    config: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Check whether a file operation is permitted given the config.

    Returns a dict with:
    - behavior: "allow" | "deny" | "ask"
    - message: str (when behavior != "allow")

    This is a simplified Python version of checkReadPermissionForTool /
    checkWritePermissionForTool — suitable for standalone use without the
    full Tool/ToolPermissionContext infrastructure.
    """
    abs_path = normalize_path_for_permission(path)

    # 1. Check for UNC paths
    if abs_path.startswith("\\\\") or abs_path.startswith("//"):
        return {
            "behavior": "ask",
            "message": (
                f"Claude requested permissions to access {path}, "
                "which appears to be a UNC path that could access network resources."
            ),
        }

    # 2. Check suspicious Windows patterns
    if has_suspicious_windows_path_pattern(abs_path):
        return {
            "behavior": "ask",
            "message": (
                f"Claude requested permissions to access {path}, "
                "which contains a suspicious Windows path pattern."
            ),
        }

    # 3. Check dangerous files (for write operations)
    if operation in ("write", "create"):
        safety = check_path_safety_for_auto_edit(path)
        if not safety["safe"]:
            return {
                "behavior": "ask",
                "message": safety.get("message", f"Access to {path} requires manual approval."),
            }

    # 4. Check if path is within allowed directories
    allowed_dirs = get_allowed_directories(config)
    if is_path_within_allowed_directories(path, allowed_dirs):
        return {"behavior": "allow"}

    # 5. Default: ask
    return {
        "behavior": "ask",
        "message": (
            f"Claude requested permissions to {'read from' if operation == 'read' else 'write to'} "
            f"{path}, but you haven't granted it yet."
        ),
    }


# ---------------------------------------------------------------------------
# Claude config / dangerous-file safety checks
# ---------------------------------------------------------------------------

def is_claude_settings_path(file_path: str) -> bool:
    """
    Returns True if the given path is a Claude settings file.
    Normalized for case-insensitive comparison.
    """
    expanded = expand_path(file_path)
    normalized = normalize_case_for_comparison(expanded)

    # .claude/settings.json or .claude/settings.local.json (any project)
    if (
        normalized.endswith(f"{sep}.claude{sep}settings.json".lower())
        or normalized.endswith(f"{sep}.claude{sep}settings.local.json".lower())
    ):
        return True

    return False


def is_claude_config_file_path(file_path: str) -> bool:
    """
    Returns True if the file is inside a protected .claude/ subdirectory
    (settings, commands, agents, skills) or is a settings file.
    """
    if is_claude_settings_path(file_path):
        return True

    cwd = os.getcwd()
    commands_dir = join(cwd, ".claude", "commands")
    agents_dir = join(cwd, ".claude", "agents")
    skills_dir = join(cwd, ".claude", "skills")

    return (
        path_in_working_path(file_path, commands_dir)
        or path_in_working_path(file_path, agents_dir)
        or path_in_working_path(file_path, skills_dir)
    )


def is_dangerous_file_path_to_auto_edit(path: str) -> bool:
    """
    Returns True if the file path points to a sensitive file that should
    not be auto-edited without explicit permission.
    """
    abs_path = expand_path(path)
    path_segments = abs_path.split(sep)
    file_name = path_segments[-1] if path_segments else ""

    # Check for UNC paths (defense-in-depth)
    if path.startswith("\\\\") or path.startswith("//"):
        return True

    # Check path segments against dangerous directories (case-insensitive)
    for i, segment in enumerate(path_segments):
        norm_segment = normalize_case_for_comparison(segment)
        for dangerous_dir in DANGEROUS_DIRECTORIES:
            if norm_segment != normalize_case_for_comparison(dangerous_dir):
                continue

            # Special case: .claude/worktrees/ is a structural path — skip it
            if dangerous_dir == ".claude":
                next_segment = path_segments[i + 1] if i + 1 < len(path_segments) else None
                if next_segment and normalize_case_for_comparison(next_segment) == "worktrees":
                    break  # Skip this .claude, continue checking

            return True

    # Check for dangerous configuration files (case-insensitive)
    if file_name:
        norm_filename = normalize_case_for_comparison(file_name)
        for dangerous_file in DANGEROUS_FILES:
            if normalize_case_for_comparison(dangerous_file) == norm_filename:
                return True

    return False


def check_path_safety_for_auto_edit(
    path: str,
    precomputed_paths_to_check: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Checks if a path is safe for auto-editing.

    Returns:
        {"safe": True} if all checks pass, or
        {"safe": False, "message": str, "classifierApprovable": bool} if unsafe.
    """
    paths_to_check = precomputed_paths_to_check or get_paths_for_permission_check(path)

    # Check for suspicious Windows path patterns
    for p in paths_to_check:
        if has_suspicious_windows_path_pattern(p):
            return {
                "safe": False,
                "message": (
                    f"Claude requested permissions to write to {path}, "
                    "which contains a suspicious Windows path pattern that requires manual approval."
                ),
                "classifierApprovable": False,
            }

    # Check for Claude config files
    for p in paths_to_check:
        if is_claude_config_file_path(p):
            return {
                "safe": False,
                "message": (
                    f"Claude requested permissions to write to {path}, "
                    "but you haven't granted it yet."
                ),
                "classifierApprovable": True,
            }

    # Check for dangerous files
    for p in paths_to_check:
        if is_dangerous_file_path_to_auto_edit(p):
            return {
                "safe": False,
                "message": (
                    f"Claude requested permissions to edit {path} "
                    "which is a sensitive file."
                ),
                "classifierApprovable": True,
            }

    return {"safe": True}


# ---------------------------------------------------------------------------
# Path containment helpers
# ---------------------------------------------------------------------------

def path_in_working_path(path: str, working_path: str) -> bool:
    """
    Returns True if `path` is equal to or nested under `working_path`.

    Mirrors the TS pathInWorkingPath function:
    - Expands both paths
    - Handles macOS /private/var, /private/tmp symlink normalization
    - Case-insensitive comparison
    """
    abs_path = expand_path(path)
    abs_working_path = expand_path(working_path)

    # Handle macOS common symlink patterns
    def _mac_normalize(p: str) -> str:
        p = p.replace("/private/var/", "/var/", 1) if p.startswith("/private/var/") else p
        if p.startswith("/private/tmp/"):
            p = "/tmp/" + p[len("/private/tmp/"):]
        elif p == "/private/tmp":
            p = "/tmp"
        return p

    norm_path = _mac_normalize(abs_path)
    norm_working = _mac_normalize(abs_working_path)

    case_norm_path = normalize_case_for_comparison(norm_path)
    case_norm_working = normalize_case_for_comparison(norm_working)

    rel = relative_path(case_norm_working, case_norm_path)

    # Same path
    if rel == "" or rel == ".":
        return True

    # Path traversal means outside
    if contains_path_traversal(rel):
        return False

    # Absolute path means outside (on POSIX)
    if PurePosixPath(rel).is_absolute():
        return False

    return True


def get_paths_for_permission_check(path: str) -> List[str]:
    """
    Returns a list of paths to check for permissions, including:
    1. The original path (normalized/expanded)
    2. The resolved symlink path (if different)

    Mirrors the TS getPathsForPermissionCheck from fsOperations.ts.
    """
    expanded = expand_path(path)
    paths = [expanded]

    try:
        resolved = realpath(expanded)
        if resolved != expanded:
            paths.append(resolved)
    except (OSError, ValueError):
        pass

    return paths


def path_in_allowed_working_path(
    path: str,
    working_directories: Optional[Set[str]] = None,
    precomputed_paths_to_check: Optional[List[str]] = None,
) -> bool:
    """
    Returns True if `path` is within any of the allowed working directories.

    working_directories: set of working directory paths (defaults to {cwd})
    precomputed_paths_to_check: pre-resolved paths (avoids redundant syscalls)
    """
    if working_directories is None:
        working_directories = {os.getcwd()}

    paths_to_check = precomputed_paths_to_check or get_paths_for_permission_check(path)

    # Resolve working directory paths as well
    resolved_working: List[str] = []
    for wp in working_directories:
        resolved_working.extend(get_paths_for_permission_check(wp))

    # All resolved forms of the input path must be within some working path
    return all(
        any(path_in_working_path(p, wp) for wp in resolved_working)
        for p in paths_to_check
    )


# ---------------------------------------------------------------------------
# Claude temp directory helpers
# ---------------------------------------------------------------------------

def get_claude_temp_dir_name() -> str:
    """
    Returns the user-specific Claude temp directory name.
    On Unix: 'claude-{uid}' to prevent multi-user permission conflicts.
    On Windows: 'claude'.
    """
    if _PLATFORM == "windows":
        return "claude"
    uid = os.getuid() if hasattr(os, "getuid") else 0
    return f"claude-{uid}"


def get_claude_temp_dir() -> str:
    """
    Returns the Claude temp directory path with trailing separator.
    Uses CLAUDE_CODE_TMPDIR env var if set, otherwise /tmp (or system tmpdir on Windows).
    Resolves symlinks (e.g. macOS /tmp → /private/tmp).
    """
    import tempfile
    base_tmp_dir = (
        os.environ.get("CLAUDE_CODE_TMPDIR")
        or (tempfile.gettempdir() if _PLATFORM == "windows" else "/tmp")
    )
    try:
        resolved_base = realpath(base_tmp_dir)
    except (OSError, ValueError):
        resolved_base = base_tmp_dir

    return join(resolved_base, get_claude_temp_dir_name()) + sep


# ---------------------------------------------------------------------------
# Pattern-based permission matching helpers (gitignore-style)
# ---------------------------------------------------------------------------

def normalize_patterns_to_path(
    patterns_by_root: Dict[Optional[str], List[str]],
    root: str,
) -> List[str]:
    """
    Normalize patterns from multiple roots relative to a single reference root.
    Patterns whose root is None can match anywhere.

    Mirrors the TS normalizePatternsToPath helper.
    """
    result: Set[str] = set()

    # None-root patterns apply everywhere
    for p in patterns_by_root.get(None, []):
        result.add(p)

    for pattern_root, patterns in patterns_by_root.items():
        if pattern_root is None:
            continue

        for pattern in patterns:
            normalized = _normalize_pattern_to_path(
                pattern_root=pattern_root,
                pattern=pattern,
                root_path=root,
            )
            if normalized:
                result.add(normalized)

    return list(result)


def _normalize_pattern_to_path(
    pattern_root: str,
    pattern: str,
    root_path: str,
) -> Optional[str]:
    """Internal helper to normalize a single pattern relative to root_path."""
    full_pattern = str(PurePosixPath(pattern_root) / pattern)

    if pattern_root == root_path:
        return "/" + pattern.lstrip("/")
    elif full_pattern.startswith(root_path + "/"):
        relative_part = full_pattern[len(root_path):]
        return "/" + relative_part.lstrip("/")
    else:
        try:
            rel = relpath(pattern_root, root_path).replace("\\", "/")
        except ValueError:
            return None
        if not rel or rel.startswith("../") or rel == "..":
            return None
        rel_pattern = rel + "/" + pattern.lstrip("/")
        return "/" + rel_pattern.lstrip("/")


# ---------------------------------------------------------------------------
# getFileReadIgnorePatterns (simplified stub)
# ---------------------------------------------------------------------------

def get_file_read_ignore_patterns(
    tool_permission_context: Optional[Dict[str, Any]] = None,
) -> Dict[Optional[str], List[str]]:
    """
    Returns deny-rule ignore patterns for file reads.
    Simplified Python version — returns empty mapping when no context provided.
    """
    return {}


# ---------------------------------------------------------------------------
# Scratchpad helpers (feature-gated)
# ---------------------------------------------------------------------------

def is_scratchpad_enabled() -> bool:
    """Check if scratchpad directory feature is enabled."""
    # In Python port, always returns False unless explicitly enabled
    return os.environ.get("CLAUDE_CODE_SCRATCHPAD_ENABLED", "").lower() in ("1", "true", "yes")


def get_project_temp_dir() -> str:
    """
    Returns the project temp directory path with trailing separator.
    Path format: /tmp/claude-{uid}/{sanitized-cwd}/
    """
    cwd = os.getcwd()
    sanitized = _sanitize_path(cwd)
    return join(get_claude_temp_dir().rstrip(sep), sanitized) + sep


def get_scratchpad_dir() -> str:
    """
    Returns the scratchpad directory path for the current session.
    Path format: /tmp/claude-{uid}/{sanitized-cwd}/{sessionId}/scratchpad/
    """
    session_id = os.environ.get("CLAUDE_SESSION_ID", "default")
    return join(get_project_temp_dir().rstrip(sep), session_id, "scratchpad")


def _sanitize_path(path: str) -> str:
    """Sanitize a path for use as a directory name (replaces / and : with _)."""
    # Replace directory separators and colons with underscores
    sanitized = path.replace("/", "_").replace("\\", "_").replace(":", "_")
    # Remove leading separators
    return sanitized.lstrip("_")


# ---------------------------------------------------------------------------
# Relative path / posix helpers
# ---------------------------------------------------------------------------

def _dir_sep() -> str:
    """Always use POSIX sep for gitignore-style pattern matching."""
    return "/"


def prepend_dir_sep(path: str) -> str:
    return "/" + path.lstrip("/")

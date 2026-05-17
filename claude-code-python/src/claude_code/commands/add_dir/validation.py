"""Add-dir validation. Ported from commands/add-dir/validation.ts."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, List, Optional, Union


# ---------------------------------------------------------------------------
# Result types (mirrors the TS discriminated union)
# ---------------------------------------------------------------------------

@dataclass
class AddDirSuccess:
    result_type: str = "success"
    absolute_path: str = ""


@dataclass
class AddDirEmptyPath:
    result_type: str = "emptyPath"


@dataclass
class AddDirPathNotFound:
    result_type: str = "pathNotFound"
    directory_path: str = ""
    absolute_path: str = ""


@dataclass
class AddDirNotADirectory:
    result_type: str = "notADirectory"
    directory_path: str = ""
    absolute_path: str = ""


@dataclass
class AddDirAlreadyInWorkingDirectory:
    result_type: str = "alreadyInWorkingDirectory"
    directory_path: str = ""
    working_dir: str = ""


AddDirectoryResult = Union[
    AddDirSuccess,
    AddDirEmptyPath,
    AddDirPathNotFound,
    AddDirNotADirectory,
    AddDirAlreadyInWorkingDirectory,
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _expand_path(path: str) -> str:
    """Expand ~ and env vars (mirrors TS expandPath)."""
    return os.path.expandvars(os.path.expanduser(path))


def _all_working_directories(permission_context: Any) -> List[str]:
    """Extract all working directories from a permission context object."""
    if permission_context is None:
        return []
    # Support dict-style and object-style contexts
    if isinstance(permission_context, dict):
        dirs = permission_context.get("working_directories", [])
        cwd = permission_context.get("cwd")
    else:
        dirs = list(getattr(permission_context, "working_directories", []) or [])
        cwd = getattr(permission_context, "cwd", None)
    if cwd and cwd not in dirs:
        dirs = [cwd] + list(dirs)
    return [d for d in dirs if d]


def _path_in_working_path(absolute_path: str, working_dir: str) -> bool:
    """Return True if *absolute_path* is inside (or equal to) *working_dir*."""
    # Normalise both paths first
    a = os.path.normpath(absolute_path)
    w = os.path.normpath(working_dir)
    # Equal, or absolute_path starts with working_dir + separator
    return a == w or a.startswith(w + os.sep)


# ---------------------------------------------------------------------------
# Core validation
# ---------------------------------------------------------------------------

async def validate_directory_for_workspace(
    directory_path: str,
    permission_context: Any = None,
) -> AddDirectoryResult:
    """
    Validate *directory_path* for addition as a working directory.

    Mirrors TS ``validateDirectoryForWorkspace``:
      1. Empty path → emptyPath
      2. Resolve + expand
      3. stat() — ENOENT / ENOTDIR / EACCES / EPERM → pathNotFound
      4. Not a directory → notADirectory
      5. Already within an existing working directory → alreadyInWorkingDirectory
      6. OK → success
    """
    if not directory_path or not directory_path.strip():
        return AddDirEmptyPath()

    # resolve() is Python's os.path.realpath / normpath equivalent
    absolute_path = os.path.normpath(_expand_path(directory_path))

    # stat the path
    try:
        stat = os.stat(absolute_path)
    except OSError as exc:
        import errno as _errno
        _NOT_FOUND_ERRNOS = {
            _errno.ENOENT, _errno.ENOTDIR, _errno.EACCES, _errno.EPERM,
        }
        if exc.errno in _NOT_FOUND_ERRNOS:
            return AddDirPathNotFound(
                directory_path=directory_path,
                absolute_path=absolute_path,
            )
        raise

    if not os.path.isdir(absolute_path):
        return AddDirNotADirectory(
            directory_path=directory_path,
            absolute_path=absolute_path,
        )

    # Check for containment in existing working directories
    for working_dir in _all_working_directories(permission_context):
        if _path_in_working_path(absolute_path, working_dir):
            return AddDirAlreadyInWorkingDirectory(
                directory_path=directory_path,
                working_dir=working_dir,
            )

    return AddDirSuccess(absolute_path=absolute_path)


# ---------------------------------------------------------------------------
# Help message
# ---------------------------------------------------------------------------

def add_dir_help_message(result: AddDirectoryResult) -> str:
    """Return a human-readable message for the given validation result."""
    rt = result.result_type

    if rt == "emptyPath":
        return "Please provide a directory path."

    if rt == "pathNotFound":
        assert isinstance(result, AddDirPathNotFound)
        return f"Path '{result.absolute_path}' was not found."

    if rt == "notADirectory":
        assert isinstance(result, AddDirNotADirectory)
        parent_dir = os.path.dirname(result.absolute_path)
        return (
            f"'{result.directory_path}' is not a directory. "
            f"Did you mean to add the parent directory '{parent_dir}'?"
        )

    if rt == "alreadyInWorkingDirectory":
        assert isinstance(result, AddDirAlreadyInWorkingDirectory)
        return (
            f"'{result.directory_path}' is already accessible within the "
            f"existing working directory '{result.working_dir}'."
        )

    if rt == "success":
        assert isinstance(result, AddDirSuccess)
        return f"Added '{result.absolute_path}' as a working directory."

    return f"Unknown result type: {rt}"


# ---------------------------------------------------------------------------
# Legacy simple helper (kept for backward compatibility)
# ---------------------------------------------------------------------------

def validate_add_dir(path: str) -> Optional[str]:
    """Return error message string or None if valid (synchronous, no context)."""
    if not path:
        return "Path is required."
    if not os.path.isabs(path):
        return f"Path must be absolute: {path}"
    if not os.path.isdir(path):
        return f"Directory does not exist: {path}"
    return None

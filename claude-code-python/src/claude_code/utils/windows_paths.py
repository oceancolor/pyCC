"""
Windows ↔ POSIX path conversion utilities.

Pure-Python port of windowsPaths.ts (windowsPathToPosixPath /
posixPathToWindowsPath) with an additional ``is_windows_path`` predicate.
No external dependencies; no subprocess calls.
"""

from __future__ import annotations

import re
import sys
from functools import lru_cache


# ---------------------------------------------------------------------------
# Predicates
# ---------------------------------------------------------------------------

# Matches  C:\...  or  C:/...  (drive-letter absolute paths)
_DRIVE_RE = re.compile(r"^[A-Za-z]:[/\\]")
# Matches  \\server\share  (UNC) or  //server/share  (POSIX UNC)
_UNC_RE = re.compile(r"^[/\\]{2}[^/\\]")
# Matches  /cygdrive/c/...
_CYGDRIVE_RE = re.compile(r"^/cygdrive/([A-Za-z])(/|$)")
# Matches  /c/...  (MSYS2 / Git Bash single-letter drive)
_MSYS_DRIVE_RE = re.compile(r"^/([A-Za-z])(/|$)")


def is_windows_path(path: str) -> bool:
    """Return True if *path* looks like a Windows-style path.

    Handles:
    - Drive-letter absolute paths (``C:\\...``, ``C:/...``)
    - UNC paths (``\\\\server\\share``)
    """
    return bool(_DRIVE_RE.match(path) or path.startswith("\\\\"))


# ---------------------------------------------------------------------------
# Conversions
# ---------------------------------------------------------------------------

@lru_cache(maxsize=512)
def to_windows_path(path: str) -> str:
    """Convert *path* to a Windows-style path (backslash separators).

    Handles:
    - Already-Windows paths — normalises slashes.
    - UNC POSIX  ``//server/share``  →  ``\\\\server\\share``
    - Cygdrive   ``/cygdrive/c/foo`` →  ``C:\\foo``
    - MSYS2      ``/c/foo``          →  ``C:\\foo``
    - Relative   ``foo/bar``         →  ``foo\\bar``
    """
    if not path:
        return path

    # Already a Windows drive-letter path — just normalise separators.
    if _DRIVE_RE.match(path):
        return path.replace("/", "\\")

    # Windows UNC already (\\server\share) — keep as-is.
    if path.startswith("\\\\"):
        return path

    # POSIX UNC  //server/share  →  \\server\share
    if path.startswith("//"):
        return path.replace("/", "\\")

    # /cygdrive/c/...  →  C:\...
    m = _CYGDRIVE_RE.match(path)
    if m:
        drive = m.group(1).upper()
        rest = path[len("/cygdrive/") + 1:]  # strip /cygdrive/X
        return drive + ":" + (rest or "\\").replace("/", "\\")

    # /c/...  →  C:\...
    m = _MSYS_DRIVE_RE.match(path)
    if m:
        drive = m.group(1).upper()
        rest = path[2:]  # strip /X
        return drive + ":" + (rest or "\\").replace("/", "\\")

    # Relative or unknown — just flip slashes.
    return path.replace("/", "\\")


@lru_cache(maxsize=512)
def from_windows_path(path: str) -> str:
    """Convert a Windows-style *path* to a POSIX path (forward slashes).

    Handles:
    - UNC  ``\\\\server\\share``  →  ``//server/share``
    - Drive  ``C:\\Users\\foo``   →  ``/c/Users/foo``
    - Already POSIX or relative   — just flip slashes.
    """
    if not path:
        return path

    # UNC  \\server\share  →  //server/share
    if path.startswith("\\\\"):
        return path.replace("\\", "/")

    # Drive-letter  C:\...  →  /c/...
    m = _DRIVE_RE.match(path)
    if m:
        drive = path[0].lower()
        rest = path[2:]  # strip  C:
        return "/" + drive + rest.replace("\\", "/")

    # Already POSIX or relative — just flip remaining backslashes.
    return path.replace("\\", "/")


# ---------------------------------------------------------------------------
# Platform convenience
# ---------------------------------------------------------------------------

def normalise_path(path: str) -> str:
    """Convert *path* to the native separator style of the current platform.

    On Windows this is equivalent to :func:`to_windows_path`; on POSIX it
    is equivalent to :func:`from_windows_path`.
    """
    if sys.platform == "win32":
        return to_windows_path(path)
    return from_windows_path(path)

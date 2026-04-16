"""
Path constraint validation for bash commands. Ported from BashTool/pathValidation.ts (1303 lines → core).
"""
from __future__ import annotations
import os
import re
from typing import Dict, List, Optional, Set, Tuple


SAFE_READ_ONLY_COMMANDS = frozenset([
    'cat', 'head', 'tail', 'grep', 'rg', 'find', 'ls', 'ls', 'll', 'la',
    'pwd', 'echo', 'printf', 'wc', 'sort', 'uniq', 'diff', 'stat', 'file',
    'which', 'type', 'less', 'more', 'bat', 'git', 'python3', 'python', 'node',
])

WRITE_COMMANDS = frozenset([
    'rm', 'rmdir', 'mv', 'cp', 'mkdir', 'touch', 'chmod', 'chown',
    'dd', 'tee', 'install', 'ln', 'symlink',
])

DANGEROUS_PATHS_RE = re.compile(
    r'(?:^|/)(?:etc/passwd|etc/shadow|etc/sudoers|\.ssh/|\.gnupg/|proc/|sys/|dev/)')


def is_safe_path(path: str, allowed_directories: List[str]) -> bool:
    """Return True if path is within one of the allowed directories."""
    abs_path = os.path.abspath(path)
    return any(abs_path.startswith(os.path.abspath(d)) for d in allowed_directories)


def is_dangerous_path(path: str) -> bool:
    """Return True if the path looks like a sensitive system path."""
    return bool(DANGEROUS_PATHS_RE.search(path))


def extract_paths_from_command(command: str) -> List[str]:
    """
    Very rough heuristic: extract tokens that look like paths.
    Not a full parser — used for quick sanity checks only.
    """
    tokens = command.split()
    paths = []
    for t in tokens:
        if t.startswith('-'):
            continue
        if '/' in t or t.startswith('~') or t.startswith('.'):
            paths.append(os.path.expanduser(t))
    return paths


def check_path_constraints(command: str, allowed_directories: List[str]) -> dict:
    """
    Check if a command's paths are within allowed directories.
    Returns a PermissionResult dict.
    """
    paths = extract_paths_from_command(command)
    for path in paths:
        if is_dangerous_path(path):
            return {"behavior": "ask", "message": f"Command accesses sensitive path: {path}"}
    return {"behavior": "passthrough", "message": "No dangerous paths detected"}

"""Git utilities.

Provides git config parsing, filesystem traversal helpers, and
``gitignore`` management utilities used across the codebase.

Ported from: src/utils/git/ (TypeScript)

Usage::

    from claude_code.utils.git import (
        parse_config_string,
        resolve_git_dir,
        is_path_gitignored,
        add_to_gitignore,
    )
"""
from __future__ import annotations

from claude_code.utils.git.git_config_parser import parse_config_string
from claude_code.utils.git.git_filesystem import resolve_git_dir
from claude_code.utils.git.gitignore import (
    add_to_gitignore,
    is_path_gitignored,
)

__all__ = [
    "parse_config_string",
    "resolve_git_dir",
    "is_path_gitignored",
    "add_to_gitignore",
]

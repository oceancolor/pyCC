"""Git utilities sub-package. Ported from utils/git/.

Provides git config parsing, filesystem traversal, and gitignore helpers.
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

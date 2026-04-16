"""
Python port of: src/utils/gitSettings.ts
Git-related configuration helpers.
"""

from __future__ import annotations

import os


def should_include_git_instructions() -> bool:
    """
    Return True if git instructions should be included in the system prompt.

    Returns False when the env var CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS is set
    to a truthy value ('1', 'true', 'yes').  Defaults to True.
    """
    val = os.environ.get("CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS", "").strip().lower()
    return val not in ("1", "true", "yes")

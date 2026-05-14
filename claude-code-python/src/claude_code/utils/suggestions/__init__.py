"""Suggestions utilities sub-package. Ported from utils/suggestions/.

Provides auto-completion and suggestion helpers for commands, directories,
shell history, and Slack channels.
"""
from __future__ import annotations

from claude_code.utils.suggestions.command_suggestions import (
    SuggestionItem,
    search_commands,
)
from claude_code.utils.suggestions.directory_completion import (
    complete_directory_path,
    get_directory_suggestions,
)

__all__ = [
    "SuggestionItem",
    "search_commands",
    "complete_directory_path",
    "get_directory_suggestions",
]

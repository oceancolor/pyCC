"""Prompt suggestion module exports."""
from claude_code.services.prompt_suggestion.prompt_suggestion import get_prompt_suggestions
from claude_code.services.prompt_suggestion.speculation import speculate

__all__ = [
    "get_prompt_suggestions",
    "speculate",
]

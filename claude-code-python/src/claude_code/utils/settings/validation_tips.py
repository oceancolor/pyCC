"""
Validation tips - provides helpful tips for settings validation errors.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


VALIDATION_TIPS: Dict[str, str] = {
    "permissions": (
        "Permissions should be a list of objects with 'toolName' (string) "
        "and 'behavior' ('allow', 'deny', or 'ask') fields."
    ),
    "hooks": (
        "Hooks should be an object mapping event names to lists of matchers. "
        "See the documentation for supported hook events."
    ),
    "model": "The 'model' field should be a string like 'claude-opus-4-5'.",
    "env": "The 'env' field should be an object of string key-value pairs.",
    "apiKeyHelper": (
        "The 'apiKeyHelper' field should be a string command that outputs "
        "an API key to stdout."
    ),
}


def get_validation_tip(field: str) -> Optional[str]:
    """Get a helpful tip for a settings field."""
    return VALIDATION_TIPS.get(field)


def get_tips_for_errors(errors: List[str]) -> List[str]:
    """Get relevant tips for a list of validation errors."""
    tips = []
    seen = set()
    for error in errors:
        for field, tip in VALIDATION_TIPS.items():
            if field in error.lower() and field not in seen:
                tips.append(tip)
                seen.add(field)
    return tips


def format_validation_error_with_tip(error: str) -> str:
    """Format a validation error with an optional tip."""
    for field, tip in VALIDATION_TIPS.items():
        if field in error.lower():
            return f"{error}\nTip: {tip}"
    return error

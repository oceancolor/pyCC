"""Process user input utilities.

Provides helpers for parsing and processing raw user input, including
slash-command detection, mention extraction, and text-prompt normalization
before the input is sent to the language model.

Ported from: src/utils/processUserInput/ (TypeScript)

Usage::

    from claude_code.utils.process_user_input import process_text_prompt
"""
from __future__ import annotations

from claude_code.utils.process_user_input.process_text_prompt import (
    process_text_prompt,
)

__all__ = [
    "process_text_prompt",
]

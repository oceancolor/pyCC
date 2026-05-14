"""Process user input utilities sub-package. Ported from utils/processUserInput/.

Provides helpers for parsing and processing user input including slash
command handling and text prompt normalization.
"""
from __future__ import annotations

from claude_code.utils.process_user_input.process_text_prompt import (
    process_text_prompt,
)

__all__ = [
    "process_text_prompt",
]

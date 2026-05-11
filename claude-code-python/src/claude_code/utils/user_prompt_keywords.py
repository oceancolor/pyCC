"""User-prompt keyword matchers. Ported from utils/userPromptKeywords.ts"""
from __future__ import annotations
import re

# ---------------------------------------------------------------------------
# Negative sentiment keywords
# ---------------------------------------------------------------------------
_NEGATIVE_PATTERN = re.compile(
    r"\b(wtf|wth|ffs|omfg|shit(?:ty|tiest)?|dumbass|horrible|awful"
    r"|piss(?:ed|ing)? off|piece of (?:shit|crap|junk)"
    r"|what the (?:fuck|hell)"
    r"|fucking? (?:broken|useless|terrible|awful|horrible)"
    r"|fuck you|screw (?:this|you)|so frustrating|this sucks|damn it)\b",
    re.IGNORECASE,
)


def matches_negative_keyword(input_text: str) -> bool:
    """Return True if *input_text* matches any negative sentiment keyword patterns."""
    return bool(_NEGATIVE_PATTERN.search(input_text))


# ---------------------------------------------------------------------------
# Keep-going / continuation keywords
# ---------------------------------------------------------------------------
_KEEP_GOING_PATTERN = re.compile(r"\b(keep going|go on)\b", re.IGNORECASE)


def matches_keep_going_keyword(input_text: str) -> bool:
    """Return True if *input_text* matches "continue", "keep going", or "go on".

    "continue" is only matched when it is the *entire* (stripped) prompt.
    "keep going" and "go on" are matched anywhere in the input.
    """
    stripped = input_text.strip()
    if stripped.lower() == "continue":
        return True
    return bool(_KEEP_GOING_PATTERN.search(stripped))

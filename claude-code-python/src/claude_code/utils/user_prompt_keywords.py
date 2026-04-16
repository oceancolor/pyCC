"""User prompt keyword detection. Ported from userPromptKeywords.ts"""
from __future__ import annotations
import re

_NEGATIVE_PATTERN = re.compile(
    r'\b(wtf|wth|ffs|omfg|shit(ty|tiest)?|dumbass|horrible|awful|piss(ed|ing)? off|'
    r'piece of (shit|crap|junk)|what the (fuck|hell)|fucking? (broken|useless|terrible|awful|horrible)|'
    r'fuck you|screw (this|you)|so frustrating|this sucks|damn it)\b', re.IGNORECASE)
_KEEP_GOING_PATTERN = re.compile(r'\b(keep going|go on)\b', re.IGNORECASE)

def matches_negative_keyword(input: str) -> bool:
    return bool(_NEGATIVE_PATTERN.search(input))

def matches_keep_going_keyword(input: str) -> bool:
    stripped = input.lower().strip()
    if stripped == 'continue':
        return True
    return bool(_KEEP_GOING_PATTERN.search(input))

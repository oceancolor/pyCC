"""
String utility functions
原始 TS: src/utils/stringUtils.ts
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any


def escape_regexp(s: str) -> str:
    """Escape special regex characters. 原始 TS: escapeRegExp"""
    return re.escape(s)


def capitalize(s: str) -> str:
    """Uppercase first character, leave rest unchanged. 原始 TS: capitalize"""
    if not s:
        return s
    return s[0].upper() + s[1:]


def plural(n: int, word: str, plural_word: Optional[str] = None) -> str:
    """Return singular or plural form. 原始 TS: plural"""
    if plural_word is None:
        plural_word = word + "s"
    return word if n == 1 else plural_word


def first_line_of(s: str) -> str:
    """Return the first line of a string. 原始 TS: firstLineOf"""
    nl = s.find("\n")
    return s if nl == -1 else s[:nl]


def count_char_in_string(s: str, char: str, start: int = 0) -> int:
    """Count occurrences of char in string. 原始 TS: countCharInString"""
    count = 0
    idx = s.find(char, start)
    while idx != -1:
        count += 1
        idx = s.find(char, idx + 1)
    return count


def normalize_full_width_digits(s: str) -> str:
    """Normalize full-width (zenkaku) digits to half-width. 原始 TS: normalizeFullWidthDigits"""
    return re.sub(
        r"[０-９]",
        lambda m: chr(ord(m.group()) - 0xFEE0),
        s,
    )


def normalize_full_width_space(s: str) -> str:
    """Normalize full-width space (U+3000) to half-width space. 原始 TS: normalizeFullWidthSpace"""
    return s.replace("\u3000", " ")


def strip_ansi(s: str) -> str:
    """Strip ANSI escape codes from a string."""
    ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
    return ansi_escape.sub("", s)


from typing import Optional

"""
sanitization.py - Unicode sanitization for hidden character attack mitigation.

Ported from sanitization.ts. Provides protection against ASCII Smuggling and
Hidden Prompt Injection attacks using invisible Unicode characters.

Reference: https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, List, TypeVar, Union, overload

T = TypeVar("T")

_MAX_ITERATIONS = 10

# Ranges that are always stripped (explicit fallback, mirrors TS)
_ZERO_WIDTH_SPACES_RE = re.compile(r"[\u200B-\u200F]")
_DIRECTIONAL_FMT_RE = re.compile(r"[\u202A-\u202E]")
_DIRECTIONAL_ISO_RE = re.compile(r"[\u2066-\u2069]")
_BOM_RE = re.compile(r"\uFEFF")
_PRIVATE_USE_RE = re.compile(r"[\uE000-\uF8FF]")


def _strip_dangerous_categories(text: str) -> str:
    """Remove characters in Unicode categories Cf (format), Co (private use), Cn (unassigned)."""
    return "".join(
        ch
        for ch in text
        if unicodedata.category(ch) not in ("Cf", "Co", "Cn")
    )


def partially_sanitize_unicode(prompt: str) -> str:
    """
    Iteratively NFKC-normalize and strip dangerous Unicode categories from
    *prompt* until it stabilises (or MAX_ITERATIONS is reached).

    Raises ValueError if the maximum iteration limit is hit (indicates a bug
    or a deliberately crafted adversarial input).
    """
    current = prompt
    previous = ""
    iterations = 0

    while current != previous and iterations < _MAX_ITERATIONS:
        previous = current

        # Step 1: NFKC normalisation
        current = unicodedata.normalize("NFKC", current)

        # Step 2: Strip by Unicode category (Cf / Co / Cn)
        current = _strip_dangerous_categories(current)

        # Step 3: Explicit range stripping (belt-and-suspenders fallback)
        current = _ZERO_WIDTH_SPACES_RE.sub("", current)
        current = _DIRECTIONAL_FMT_RE.sub("", current)
        current = _DIRECTIONAL_ISO_RE.sub("", current)
        current = _BOM_RE.sub("", current)
        current = _PRIVATE_USE_RE.sub("", current)

        iterations += 1

    if iterations >= _MAX_ITERATIONS:
        raise ValueError(
            f"Unicode sanitization reached maximum iterations ({_MAX_ITERATIONS}) "
            f"for input: {prompt[:100]}"
        )

    return current


def recursively_sanitize_unicode(value: Any) -> Any:
    """
    Recursively sanitize all strings inside *value* (str, list, or dict).
    Numbers, booleans, and None pass through unchanged.
    """
    if isinstance(value, str):
        return partially_sanitize_unicode(value)

    if isinstance(value, list):
        return [recursively_sanitize_unicode(item) for item in value]

    if isinstance(value, dict):
        return {
            recursively_sanitize_unicode(k): recursively_sanitize_unicode(v)
            for k, v in value.items()
        }

    # Primitives (int, float, bool, None, …) pass through unchanged
    return value

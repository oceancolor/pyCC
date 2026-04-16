"""
PDF utils - Python port of pdfUtils.ts

Supplements pdf.py with:
- DOCUMENT_EXTENSIONS constant
- parse_pdf_page_range(pages) → (first, last) | None
- is_pdf_supported() → bool   (Haiku 3 doesn't support PDF blocks)
- is_pdf_extension(ext) → bool

Note: pdf.py handles low-level read/encode/extract; this module mirrors
the higher-level pdfUtils.ts helpers used by tool dispatch logic.
"""
from __future__ import annotations

import math
from typing import Optional, Tuple

# Document extensions handled specially (passed as document blocks, not text)
DOCUMENT_EXTENSIONS: frozenset[str] = frozenset({"pdf"})


def parse_pdf_page_range(pages: str) -> Optional[Tuple[int, float]]:
    """Parse a page range string into (first_page, last_page).

    Supported formats:
      "5"   → (5, 5)
      "1-10"→ (1, 10)
      "3-"  → (3, inf)

    Returns None on invalid input (non-numeric, zero, inverted range).
    Pages are 1-indexed.
    """
    trimmed = pages.strip()
    if not trimmed:
        return None

    # "N-" open-ended range
    if trimmed.endswith("-"):
        prefix = trimmed[:-1]
        try:
            first = int(prefix)
        except ValueError:
            return None
        if first < 1:
            return None
        return (first, math.inf)

    dash_idx = trimmed.find("-")

    if dash_idx == -1:
        # Single page
        try:
            page = int(trimmed)
        except ValueError:
            return None
        if page < 1:
            return None
        return (page, page)

    # Range "1-10"
    try:
        first = int(trimmed[:dash_idx])
        last = int(trimmed[dash_idx + 1:])
    except ValueError:
        return None

    if first < 1 or last < 1 or last < first:
        return None
    return (first, last)


def is_pdf_supported(model_name: Optional[str] = None) -> bool:
    """Return True if PDF document blocks are supported by the current model.

    PDF blocks work on all providers except claude-3-haiku (pre-PDF era).
    Pass model_name explicitly; if None, tries to import from model utils.
    """
    if model_name is None:
        try:
            from claude_code.utils.model_utils import get_main_loop_model  # type: ignore
            model_name = get_main_loop_model()
        except Exception:
            return True  # default to supported

    return "claude-3-haiku" not in model_name.lower()


def is_pdf_extension(ext: str) -> bool:
    """Return True if the extension (with or without leading dot) is PDF."""
    normalized = ext.lstrip(".").lower()
    return normalized in DOCUMENT_EXTENSIONS

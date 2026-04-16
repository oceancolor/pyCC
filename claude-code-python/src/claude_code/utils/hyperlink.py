"""
OSC 8 hyperlink support for terminal output. Ported from hyperlink.ts
"""
from __future__ import annotations
import os

OSC8_START = "\x1b]8;;"
OSC8_END = "\x07"


def _supports_hyperlinks() -> bool:
    term = os.environ.get("TERM", "")
    colorterm = os.environ.get("COLORTERM", "")
    term_program = os.environ.get("TERM_PROGRAM", "")
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    if term_program in ("iTerm.app", "WezTerm", "Hyper"):
        return True
    if colorterm in ("truecolor", "24bit"):
        return True
    return False


def create_hyperlink(url: str, content: str = "", supports: bool | None = None) -> str:
    """Create an OSC 8 clickable hyperlink, fallback to plain URL."""
    has_support = _supports_hyperlinks() if supports is None else supports
    if not has_support:
        return url
    display = content if content else url
    return f"{OSC8_START}{url}{OSC8_END}{display}{OSC8_START}{OSC8_END}"

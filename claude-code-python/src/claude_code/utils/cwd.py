"""
Current working directory utility
原始 TS: src/utils/cwd.ts
"""
from __future__ import annotations

import os
import unicodedata


def get_cwd() -> str:
    """
    Get the current working directory, NFC normalized.
    原始 TS: getCwd
    """
    cwd = os.getcwd()
    return unicodedata.normalize("NFC", cwd)


def set_cwd(path: str) -> None:
    """
    Set the current working directory.
    原始 TS: setCwd (via process.chdir)
    """
    os.chdir(path)

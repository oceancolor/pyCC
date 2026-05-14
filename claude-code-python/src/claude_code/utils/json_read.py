"""JSON read helpers. Ported from jsonRead.ts.

Provides safe JSON file reading with UTF-8 BOM stripping, lenient error
handling, and optional schema validation.
"""
from __future__ import annotations

import json
import os
from typing import Any, Callable, Optional, Type, TypeVar

__all__ = [
    "UTF8_BOM",
    "strip_bom",
    "read_json_file",
    "read_json_file_safe",
    "parse_json_safe",
    "write_json_file",
]

UTF8_BOM = "\uFEFF"

T = TypeVar("T")


def strip_bom(content: str) -> str:
    """Strip a leading UTF-8 Byte Order Mark from *content*.

    PowerShell 5.x writes UTF-8 with BOM by default (``Out-File``,
    ``Set-Content``).  Without stripping, ``json.loads`` raises
    ``JSONDecodeError: Unexpected BOM``.

    Ported from utils/jsonRead.ts: stripBOM.
    """
    return content[1:] if content.startswith(UTF8_BOM) else content


def parse_json_safe(text: str, default: Any = None) -> Any:
    """Parse *text* as JSON, returning *default* on any error."""
    try:
        return json.loads(strip_bom(text))
    except (json.JSONDecodeError, ValueError):
        return default


def read_json_file(path: str) -> Any:
    """Read and parse a JSON file, stripping any leading BOM.

    Returns the parsed Python object.  Raises IOError or JSONDecodeError
    on failure.
    """
    with open(path, encoding="utf-8-sig") as fh:
        return json.loads(strip_bom(fh.read()))


def read_json_file_safe(path: str, default: Any = None) -> Any:
    """Read and parse a JSON file, returning *default* on any error."""
    try:
        return read_json_file(path)
    except Exception:
        return default


def write_json_file(path: str, data: Any, indent: int = 2) -> None:
    """Serialise *data* to *path* as pretty-printed JSON (UTF-8, no BOM).

    Creates parent directories if they do not exist.
    """
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=indent, ensure_ascii=False)
        fh.write("\n")

"""JSON read helpers. Ported from utils/jsonRead.ts"""
from __future__ import annotations

UTF8_BOM = "\uFEFF"


def strip_bom(content: str) -> str:
    """Strip a leading UTF-8 Byte Order Mark from *content*.

    PowerShell 5.x writes UTF-8 with BOM by default (``Out-File``,
    ``Set-Content``).  Without stripping, ``json.loads`` raises
    ``JSONDecodeError: Unexpected BOM``.

    Ported from utils/jsonRead.ts: stripBOM.
    """
    return content[1:] if content.startswith(UTF8_BOM) else content


def read_json_file(path: str) -> object:
    """Read and parse a JSON file, stripping any leading BOM.

    Returns the parsed Python object, or raises on IO / parse errors.
    """
    import json
    with open(path, encoding="utf-8-sig") as fh:
        # ``utf-8-sig`` codec automatically strips the BOM on read,
        # but we also call strip_bom() for safety with other codecs.
        return json.loads(strip_bom(fh.read()))

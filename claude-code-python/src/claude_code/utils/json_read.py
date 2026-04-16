"""
UTF-8 BOM stripping for JSON reads.
Port of utils/jsonRead.ts
"""

UTF8_BOM = "\uFEFF"


def strip_bom(content: str) -> str:
    """Strip UTF-8 BOM (U+FEFF) from content if present.

    PowerShell 5.x writes UTF-8 with BOM by default.
    Without stripping, json.loads fails with a parse error.
    """
    return content[1:] if content.startswith(UTF8_BOM) else content

"""
XML/HTML escaping utilities.
Ported from utils/xml.ts
"""
from __future__ import annotations


def escape_xml(s: str) -> str:
    """Escape XML/HTML special characters for safe interpolation into element
    text content (between tags).

    Use when untrusted strings (process stdout, user input, external data)
    go inside ``<tag>${here}</tag>``.
    """
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_xml_attr(s: str) -> str:
    """Escape for interpolation into a double- or single-quoted attribute value:
    ``<tag attr="${here}">``.

    Escapes quotes in addition to ``& < >``.
    """
    return escape_xml(s).replace('"', "&quot;").replace("'", "&apos;")

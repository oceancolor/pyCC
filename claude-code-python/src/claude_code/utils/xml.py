"""XML/HTML escaping utilities. Ported from xml.ts.

Provides safe string escaping for interpolating untrusted content into
XML/HTML element bodies and attribute values.
"""
from __future__ import annotations

import re
from html import escape as _html_escape, unescape as _html_unescape
from typing import Optional

__all__ = [
    "escape_xml",
    "escape_xml_attr",
    "unescape_xml",
    "wrap_in_tag",
    "strip_xml_tags",
    "is_valid_xml_tag_name",
]

_TAG_NAME_RE = re.compile(r"^[A-Za-z_][\w.\-]*$")


def escape_xml(s: str) -> str:
    """Escape XML/HTML special characters for safe interpolation into element
    text content (between tags).

    Escapes ``& < >`` — use when untrusted strings go inside
    ``<tag>${here}</tag>``.
    """
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def escape_xml_attr(s: str) -> str:
    """Escape for interpolation into a double-quoted XML attribute value:
    ``<tag attr="${here}">``.

    Escapes ``& < > " '`` so the value is safe in both single- and
    double-quoted attribute contexts.
    """
    return (
        escape_xml(s)
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def unescape_xml(s: str) -> str:
    """Reverse-escape XML/HTML entities back to their character equivalents."""
    return _html_unescape(s)


def wrap_in_tag(content: str, tag: str, attrs: Optional[dict[str, str]] = None) -> str:
    """Wrap *content* in an XML *tag*.

    Example::

        wrap_in_tag("hello & world", "p")
        # → "<p>hello &amp; world</p>"

        wrap_in_tag("text", "span", {"class": "highlight"})
        # → '<span class="highlight">text</span>'
    """
    if not is_valid_xml_tag_name(tag):
        raise ValueError(f"Invalid XML tag name: {tag!r}")
    attr_str = ""
    if attrs:
        attr_str = " " + " ".join(
            f'{k}="{escape_xml_attr(v)}"' for k, v in attrs.items()
        )
    return f"<{tag}{attr_str}>{escape_xml(content)}</{tag}>"


def strip_xml_tags(s: str) -> str:
    """Remove all XML/HTML tags from *s*, leaving only text content."""
    return re.sub(r"<[^>]+>", "", s)


def is_valid_xml_tag_name(name: str) -> bool:
    """Return True if *name* is a valid XML element name."""
    return bool(_TAG_NAME_RE.match(name))

"""WebFetchTool utilities. Ported from WebFetchTool/utils.ts"""
from __future__ import annotations
import re
from urllib.parse import urlparse


def normalize_url(url: str) -> str:
    """Upgrade http:// to https:// and return a normalized URL."""
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url


def is_binary_content_type(content_type: str) -> bool:
    """Return True for binary content types that should not be processed as text."""
    binary_types = (
        "application/octet-stream",
        "application/pdf",
        "application/zip",
        "application/x-zip",
        "application/x-gzip",
        "image/",
        "audio/",
        "video/",
    )
    ct_lower = content_type.lower().split(";")[0].strip()
    return any(ct_lower.startswith(bt) for bt in binary_types)


def extract_hostname(url: str) -> str:
    """Extract the hostname from a URL."""
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def extract_pathname(url: str) -> str:
    """Extract the pathname from a URL."""
    try:
        return urlparse(url).path or "/"
    except Exception:
        return "/"

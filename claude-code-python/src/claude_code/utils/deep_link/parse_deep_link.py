"""Deep link URI parser. Ported from utils/deepLink/parseDeepLink.ts"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse, parse_qs, urlencode, unquote_plus

DEEP_LINK_PROTOCOL = "claude-cli"

# GitHub owner/repo slug: alphanumerics, dots, hyphens, underscores, one slash.
_REPO_SLUG_PATTERN = re.compile(r'^[\w.\-]+/[\w.\-]+$')

MAX_QUERY_LENGTH = 5000
MAX_CWD_LENGTH = 4096


@dataclass
class DeepLinkAction:
    """Parsed representation of a claude-cli:// deep link."""

    query: Optional[str] = None
    cwd: Optional[str] = None
    repo: Optional[str] = None


def _contains_control_chars(s: str) -> bool:
    """Check if a string contains ASCII control characters (0x00–0x1F, 0x7F)."""
    for ch in s:
        code = ord(ch)
        if code <= 0x1F or code == 0x7F:
            return True
    return False


def _partially_sanitize_unicode(text: str) -> str:
    """Strip hidden Unicode characters used for ASCII smuggling / prompt injection.

    Removes Unicode format characters (category Cf) that are invisible but can
    be used to hide content from humans while the model still processes them.
    """
    import unicodedata
    return "".join(ch for ch in text if unicodedata.category(ch) != "Cf")


def parse_deep_link(uri: str) -> DeepLinkAction:
    """Parse a claude-cli:// URI into a structured action.

    Args:
        uri: The raw URI string, e.g. ``claude-cli://open?q=hello+world``.

    Returns:
        A :class:`DeepLinkAction` with optional query, cwd, and repo fields.

    Raises:
        ValueError: If the URI is malformed or contains dangerous characters.
    """
    # Normalize: accept with or without the double slash
    if uri.startswith(f"{DEEP_LINK_PROTOCOL}://"):
        normalized = uri
    elif uri.startswith(f"{DEEP_LINK_PROTOCOL}:"):
        normalized = uri.replace(f"{DEEP_LINK_PROTOCOL}:", f"{DEEP_LINK_PROTOCOL}://", 1)
    else:
        raise ValueError(
            f"Invalid deep link: expected {DEEP_LINK_PROTOCOL}:// scheme, got \"{uri}\""
        )

    try:
        parsed = urlparse(normalized)
    except Exception:
        raise ValueError(f"Invalid deep link URL: \"{uri}\"")

    if parsed.hostname != "open":
        raise ValueError(f"Unknown deep link action: \"{parsed.hostname}\"")

    params = parse_qs(parsed.query, keep_blank_values=True)

    def _first(key: str) -> Optional[str]:
        vals = params.get(key)
        return vals[0] if vals else None

    cwd = _first("cwd")
    repo = _first("repo")
    raw_query = _first("q")

    # Validate cwd
    if cwd:
        if not (cwd.startswith("/") or re.match(r'^[a-zA-Z]:[/\\]', cwd)):
            raise ValueError(
                f"Invalid cwd in deep link: must be an absolute path, got \"{cwd}\""
            )
        if _contains_control_chars(cwd):
            raise ValueError("Deep link cwd contains disallowed control characters")
        if len(cwd) > MAX_CWD_LENGTH:
            raise ValueError(
                f"Deep link cwd exceeds {MAX_CWD_LENGTH} characters (got {len(cwd)})"
            )

    # Validate repo slug
    if repo and not _REPO_SLUG_PATTERN.match(repo):
        raise ValueError(
            f"Invalid repo in deep link: expected \"owner/repo\", got \"{repo}\""
        )

    # Validate and sanitize query
    query: Optional[str] = None
    if raw_query and raw_query.strip():
        query = _partially_sanitize_unicode(raw_query.strip())
        if _contains_control_chars(query):
            raise ValueError("Deep link query contains disallowed control characters")
        if len(query) > MAX_QUERY_LENGTH:
            raise ValueError(
                f"Deep link query exceeds {MAX_QUERY_LENGTH} characters (got {len(query)})"
            )

    return DeepLinkAction(query=query, cwd=cwd, repo=repo)


def build_deep_link(action: DeepLinkAction) -> str:
    """Build a claude-cli:// deep link URL from a :class:`DeepLinkAction`."""
    params: dict = {}
    if action.query:
        params["q"] = action.query
    if action.cwd:
        params["cwd"] = action.cwd
    if action.repo:
        params["repo"] = action.repo

    query_string = urlencode(params) if params else ""
    base = f"{DEEP_LINK_PROTOCOL}://open"
    return f"{base}?{query_string}" if query_string else base

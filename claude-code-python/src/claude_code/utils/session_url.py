"""
Session URL parsing - Python port of sessionUrl.ts

Provides parse_session_identifier(resume_identifier) which handles:
  - JSONL file paths (ends with .jsonl)
  - Plain UUIDs
  - Full URLs (http/https)

Returns a ParsedSessionUrl dataclass or None if invalid.
"""
from __future__ import annotations

import uuid as _uuid_mod
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass
class ParsedSessionUrl:
    session_id: str          # UUID string
    ingress_url: Optional[str]
    is_url: bool
    jsonl_file: Optional[str]
    is_jsonl_file: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _validate_uuid(value: str) -> bool:
    """Return True if *value* is a valid UUID (any version)."""
    try:
        _uuid_mod.UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def _random_uuid() -> str:
    return str(_uuid_mod.uuid4())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_session_identifier(resume_identifier: str) -> Optional[ParsedSessionUrl]:
    """Parse a session resume identifier.

    Handles:
    - JSONL file paths  → is_jsonl_file=True, fresh session_id
    - Plain UUID        → is_url=False, session_id=the UUID
    - http/https URL    → is_url=True, fresh session_id, ingress_url=href

    Returns None if the identifier is unrecognisable.
    """
    # Check for JSONL path first (before URL parse, handles Windows drive letters)
    if resume_identifier.lower().endswith(".jsonl"):
        return ParsedSessionUrl(
            session_id=_random_uuid(),
            ingress_url=None,
            is_url=False,
            jsonl_file=resume_identifier,
            is_jsonl_file=True,
        )

    # Plain UUID?
    if _validate_uuid(resume_identifier):
        return ParsedSessionUrl(
            session_id=resume_identifier,
            ingress_url=None,
            is_url=False,
            jsonl_file=None,
            is_jsonl_file=False,
        )

    # URL?
    try:
        parsed = urlparse(resume_identifier)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            return ParsedSessionUrl(
                session_id=_random_uuid(),
                ingress_url=resume_identifier,
                is_url=True,
                jsonl_file=None,
                is_jsonl_file=False,
            )
    except Exception:
        pass

    return None

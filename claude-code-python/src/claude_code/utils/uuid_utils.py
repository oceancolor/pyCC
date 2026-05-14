"""UUID generation and validation utilities. Ported from uuid.ts.

Thin wrappers around Python's standard ``uuid`` module that mirror the
TypeScript API surface used across the codebase.
"""
from __future__ import annotations

import re
import uuid as _uuid
from typing import Optional

__all__ = [
    "new_uuid",
    "short_uuid",
    "is_valid_uuid",
    "generate_request_id",
    "generate_session_id",
    "uuid_to_bytes",
    "bytes_to_uuid",
]

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def new_uuid() -> str:
    """Return a new random UUID v4 string (hyphenated, lowercase)."""
    return str(_uuid.uuid4())


def short_uuid(length: int = 8) -> str:
    """Return a URL-safe UUID-derived string of *length* hex characters.

    Uses UUID4 randomness without hyphens, truncated to *length*.
    """
    if length < 1 or length > 32:
        raise ValueError(f"length must be between 1 and 32, got {length}")
    return str(_uuid.uuid4()).replace("-", "")[:length]


def is_valid_uuid(s: str) -> bool:
    """Return True if *s* is a valid UUID in the standard hyphenated form."""
    return bool(_UUID_RE.match(s))


def generate_request_id() -> str:
    """Generate a unique request ID (same as new_uuid)."""
    return new_uuid()


def generate_session_id() -> str:
    """Generate a unique session ID prefixed with 'sess_'."""
    return f"sess_{short_uuid(24)}"


def uuid_to_bytes(uuid_str: str) -> bytes:
    """Convert a UUID string to its 16-byte binary representation."""
    return _uuid.UUID(uuid_str).bytes


def bytes_to_uuid(b: bytes) -> str:
    """Convert 16 bytes to the standard UUID string form."""
    return str(_uuid.UUID(bytes=b))

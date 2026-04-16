"""
UUID validation and creation utilities.
Port of utils/uuid.ts
"""
import re
import secrets
from typing import Optional

UUID_REGEX = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_uuid(maybe_uuid: object) -> Optional[str]:
    """Validate a UUID string. Returns the UUID string or None if invalid."""
    if not isinstance(maybe_uuid, str):
        return None
    return maybe_uuid if UUID_REGEX.match(maybe_uuid) else None


def create_agent_id(label: Optional[str] = None) -> str:
    """Generate a new agent ID with optional label prefix.

    Format: a{label-}{16 hex chars}
    Example: aa3f2c1b4d5e6f7a8, acompact-a3f2c1b4d5e6f7a8
    """
    suffix = secrets.token_hex(8)
    return f"a{label}-{suffix}" if label else f"a{suffix}"

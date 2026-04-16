"""
Tagged ID encoding compatible with API's tagged_id.py format.
Ported from taggedId.ts
"""
from __future__ import annotations

BASE58_CHARS = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
VERSION = "01"
ENCODED_LENGTH = 22


def _base58_encode(n: int) -> str:
    base = len(BASE58_CHARS)
    result = [BASE58_CHARS[0]] * ENCODED_LENGTH
    i = ENCODED_LENGTH - 1
    while n > 0:
        result[i] = BASE58_CHARS[n % base]
        n //= base
        i -= 1
    return "".join(result)


def _uuid_to_int(uuid: str) -> int:
    hex_str = uuid.replace("-", "")
    if len(hex_str) != 32:
        raise ValueError(f"Invalid UUID: {uuid}")
    return int(hex_str, 16)


def to_tagged_id(tag: str, uuid: str) -> str:
    """Convert a UUID to a tagged ID like 'user_01PaGUP2rbg1XDh7Z9W1CEpd'."""
    n = _uuid_to_int(uuid)
    return f"{tag}_{VERSION}{_base58_encode(n)}"

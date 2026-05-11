"""Hash utilities. Ported from utils/hash.ts"""
from __future__ import annotations
import hashlib


def djb2_hash(s: str) -> int:
    """djb2 string hash — fast non-cryptographic hash returning a signed 32-bit int.

    Deterministic across runtimes (unlike platform-specific hash seeds).
    Use as a fallback when a stable, on-disk-safe hash is needed
    (e.g., cache directory names that must survive runtime upgrades).

    Ported from utils/hash.ts: djb2Hash.
    """
    h = 0
    for ch in s:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    # Convert to signed 32-bit int (mirror the TypeScript ``| 0`` behaviour)
    if h >= 0x80000000:
        h -= 0x100000000
    return h


def hash_content(content: str) -> str:
    """Hash arbitrary content for change detection.

    Uses SHA-256 (fast enough for diff detection; not cryptographically
    sensitive). Mirrors the Node.js path in utils/hash.ts: hashContent.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def hash_pair(a: str, b: str) -> str:
    """Hash two strings without allocating a concatenated temporary string.

    Uses incremental SHA-256 update with a NUL separator to distinguish
    ``("ts", "code")`` from ``("tsc", "ode")``.  Mirrors the Node.js path in
    utils/hash.ts: hashPair.
    """
    h = hashlib.sha256()
    h.update(a.encode("utf-8"))
    h.update(b"\x00")
    h.update(b.encode("utf-8"))
    return h.hexdigest()

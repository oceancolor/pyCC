"""
Semver comparison utilities.
Port of utils/semver.ts
"""
from typing import Literal

from packaging.version import Version


def _parse(v: str) -> Version:
    try:
        return Version(v)
    except Exception:
        # Loose parsing: strip leading 'v' etc.
        return Version(v.lstrip("vV"))


def gt(a: str, b: str) -> bool:
    """Return True if version a > b."""
    return _parse(a) > _parse(b)


def gte(a: str, b: str) -> bool:
    """Return True if version a >= b."""
    return _parse(a) >= _parse(b)


def lt(a: str, b: str) -> bool:
    """Return True if version a < b."""
    return _parse(a) < _parse(b)


def lte(a: str, b: str) -> bool:
    """Return True if version a <= b."""
    return _parse(a) <= _parse(b)


def order(a: str, b: str) -> Literal[-1, 0, 1]:
    """Return -1, 0, or 1 for a compared to b."""
    va, vb = _parse(a), _parse(b)
    if va < vb:
        return -1
    if va > vb:
        return 1
    return 0


def satisfies(version: str, range_str: str) -> bool:
    """Check if version satisfies a simple range like '>=1.2.3' or '^2.0.0'."""
    import re

    v = _parse(version)
    # Handle simple operators: >=, <=, >, <, =, ^, ~
    m = re.match(r"^([><=^~!]+)\s*([\d.]+)", range_str.strip())
    if not m:
        return str(v) == range_str.strip()
    op, bound = m.group(1), m.group(2)
    bv = _parse(bound)
    if op in (">=",):
        return v >= bv
    if op in (">",):
        return v > bv
    if op in ("<=",):
        return v <= bv
    if op in ("<",):
        return v < bv
    if op in ("=", "=="):
        return v == bv
    if op == "^":
        # Compatible release: same major
        return v >= bv and v.major == bv.major
    if op == "~":
        # Patch compatible: same major.minor
        return v >= bv and v.major == bv.major and v.minor == bv.minor
    return False

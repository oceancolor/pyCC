"""
Plugin versioning - manages plugin version resolution and comparisons.
"""

from __future__ import annotations

import re
from typing import Optional, Tuple


def parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse a version string into (major, minor, patch)."""
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", version_str.strip())
    if match:
        return int(match.group(1)), int(match.group(2)), int(match.group(3))
    # Try simple numeric
    match = re.match(r"^v?(\d+)", version_str.strip())
    if match:
        return int(match.group(1)), 0, 0
    return 0, 0, 0


def compare_versions(v1: str, v2: str) -> int:
    """
    Compare two version strings.
    Returns: -1 if v1 < v2, 0 if equal, 1 if v1 > v2.
    """
    t1 = parse_version(v1)
    t2 = parse_version(v2)
    if t1 < t2:
        return -1
    if t1 > t2:
        return 1
    return 0


def is_newer_version(current: str, candidate: str) -> bool:
    """Check if candidate version is newer than current."""
    return compare_versions(candidate, current) > 0


def satisfies_version_range(version: str, range_spec: str) -> bool:
    """
    Check if a version satisfies a range specification.
    Simplified: supports exact, ^, ~, >=, <=.
    """
    version_tuple = parse_version(version)

    range_spec = range_spec.strip()
    if range_spec.startswith("^"):
        min_v = parse_version(range_spec[1:])
        return version_tuple >= min_v and version_tuple[0] == min_v[0]
    elif range_spec.startswith("~"):
        min_v = parse_version(range_spec[1:])
        return version_tuple >= min_v and version_tuple[:2] == min_v[:2]
    elif range_spec.startswith(">="):
        min_v = parse_version(range_spec[2:])
        return version_tuple >= min_v
    elif range_spec.startswith("<="):
        max_v = parse_version(range_spec[2:])
        return version_tuple <= max_v
    elif range_spec == "*" or range_spec == "":
        return True
    else:
        # Exact match
        return parse_version(version) == parse_version(range_spec)

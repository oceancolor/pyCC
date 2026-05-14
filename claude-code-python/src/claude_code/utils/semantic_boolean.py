"""Semantic boolean coercion. Ported from semanticBoolean.ts.

Tool inputs arrive as model-generated JSON.  The model occasionally quotes
booleans — "replace_all":"false" instead of "replace_all":false — and a
strict boolean check rejects that with a type error.  This module provides
lenient parsing that treats the string literals "true"/"false"/"yes"/"no"
as their boolean equivalents.
"""
from __future__ import annotations

from typing import Optional


_TRUTHY = frozenset({"true", "yes", "1", "on", "enabled"})
_FALSY = frozenset({"false", "no", "0", "off", "disabled"})


def parse_semantic_boolean(value: object) -> Optional[bool]:
    """Convert *value* to bool, accepting string literals.

    Returns:
        True  – if value is True or a truthy string literal
        False – if value is False or a falsy string literal
        None  – if value is None or unrecognised

    Raises:
        TypeError – if value is an unrecognised non-string, non-None type
    """
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    if isinstance(value, str):
        low = value.strip().lower()
        if low in _TRUTHY:
            return True
        if low in _FALSY:
            return False
        return None
    if isinstance(value, (int, float)):
        return bool(value)
    raise TypeError(f"Cannot coerce {type(value).__name__!r} to bool")


def semantic_boolean(value: object, default: Optional[bool] = None) -> Optional[bool]:
    """Like parse_semantic_boolean but returns *default* instead of None."""
    result = parse_semantic_boolean(value)
    return default if result is None else result


def coerce_bool(value: object) -> bool:
    """Strict coercion – raises ValueError if *value* is unrecognised."""
    result = parse_semantic_boolean(value)
    if result is None:
        raise ValueError(f"Cannot coerce {value!r} to bool")
    return result

"""
Semantic number/boolean — coerce string literals from model JSON.
Ported from semanticNumber.ts and semanticBoolean.ts
"""
from __future__ import annotations
import re
from typing import Any, Optional, Union


def parse_semantic_number(v: Any) -> Any:
    """Coerce numeric string literals to float. Returns original if not a numeric string."""
    if isinstance(v, str) and re.match(r'^-?\d+(\.\d+)?$', v):
        try:
            return float(v) if '.' in v else int(v)
        except ValueError:
            pass
    return v


def parse_semantic_boolean(v: Any) -> Any:
    """Coerce 'true'/'false' strings to bool. Returns original otherwise."""
    if v == 'true':
        return True
    if v == 'false':
        return False
    return v


def semantic_number(v: Any, default: Any = None) -> Optional[Union[int, float]]:
    result = parse_semantic_number(v)
    if isinstance(result, (int, float)):
        return result
    return default


def semantic_boolean(v: Any, default: Any = None) -> Optional[bool]:
    result = parse_semantic_boolean(v)
    if isinstance(result, bool):
        return result
    return default

"""Policy limits. Stub."""
from __future__ import annotations
from typing import Any, Dict, Optional


def get_policy_limits() -> Dict[str, Any]:
    return {}


def check_policy_limit(feature: str) -> bool:
    return True

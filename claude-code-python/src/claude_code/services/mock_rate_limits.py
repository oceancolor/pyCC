"""Mock rate limits for ANT-only testing. Ported from services/mockRateLimits.ts (stub)"""
from __future__ import annotations
import os
from typing import Dict, Optional


def should_process_mock_limits() -> bool:
    return os.environ.get("USER_TYPE") == "ant" and \
           os.environ.get("CLAUDE_CODE_MOCK_LIMITS_ACTIVE", "").lower() in ("1", "true")


def apply_mock_headers(headers: Dict[str, str]) -> Dict[str, str]:
    return headers  # stub: no-op


def get_mock_headers() -> Optional[Dict[str, str]]:
    return None


def get_mock_headerless_429_message() -> Optional[str]:
    return None


def is_mock_fast_mode_rate_limit_scenario() -> bool:
    return False


def check_mock_fast_mode_rate_limit(is_fast_mode_active: bool = False) -> Optional[Dict]:
    return None

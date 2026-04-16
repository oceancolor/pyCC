"""Rate limit mocking facade. Ported from services/rateLimitMocking.ts"""
from __future__ import annotations
import os
from typing import Dict, Optional


def _should_process_mock_limits() -> bool:
    return os.environ.get("USER_TYPE") == "ant" and \
           os.environ.get("CLAUDE_CODE_MOCK_LIMITS_ACTIVE", "").lower() in ("1", "true")

should_process_mock_limits = _should_process_mock_limits


def process_rate_limit_headers(headers: Dict[str, str]) -> Dict[str, str]:
    if _should_process_mock_limits():
        from claude_code.services.mock_rate_limits import apply_mock_headers
        return apply_mock_headers(headers)
    return headers


def should_process_rate_limits(is_subscriber: bool) -> bool:
    return is_subscriber or _should_process_mock_limits()


def check_mock_rate_limit_error(current_model: str, is_fast_mode_active: bool = False) -> Optional[Exception]:
    if not _should_process_mock_limits():
        return None
    return None  # Stub: no mock error


def is_mock_rate_limit_error(error: Exception) -> bool:
    return _should_process_mock_limits() and getattr(error, "status_code", 0) == 429

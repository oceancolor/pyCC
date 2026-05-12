"""
logging.py - API logging and metrics opt-out utilities.

Port of TypeScript logging.ts.
"""

import logging
import os
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)

_metrics_status_cache: Optional[Dict[str, Any]] = None


async def check_metrics_enabled() -> Dict[str, Any]:
    """
    Check if metrics export is enabled for the current organization.

    Returns:
        Dict with 'enabled' bool and optional 'reason' string.
    """
    global _metrics_status_cache

    if _metrics_status_cache is not None:
        return _metrics_status_cache

    # Check local env override
    if os.environ.get('DISABLE_METRICS', '').lower() in ('1', 'true'):
        _metrics_status_cache = {'enabled': False, 'reason': 'env_disabled'}
        return _metrics_status_cache

    # Default: enabled
    _metrics_status_cache = {'enabled': True}
    return _metrics_status_cache


def clear_metrics_cache() -> None:
    """Clear the metrics status cache."""
    global _metrics_status_cache
    _metrics_status_cache = None


def create_api_logger(
    session_id: str,
    write_to_file: bool = False,
) -> Dict[str, Any]:
    """
    Create an API request/response logger.

    Args:
        session_id: Session identifier for log files
        write_to_file: Whether to write logs to file

    Returns:
        Logger object with 'log_request' and 'log_response' callables.
    """
    api_logger = logging.getLogger(f'claude-code.api.{session_id[:8]}')

    def log_request(url: str, body: Any) -> None:
        if api_logger.isEnabledFor(logging.DEBUG):
            api_logger.debug(f'API request to {url}')

    def log_response(
        url: str,
        status: int,
        body: Any,
        duration_ms: float,
    ) -> None:
        if api_logger.isEnabledFor(logging.DEBUG):
            api_logger.debug(f'API response from {url}: {status} ({duration_ms:.0f}ms)')

    return {
        'log_request': log_request,
        'log_response': log_response,
    }

"""
session_ingress.py - Session ingress/analytics utilities.

Port of TypeScript sessionIngress.ts.
"""

import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

SESSION_INGRESS_ENDPOINT = '/api/claude_code/session_ingress'


async def report_session_start(
    session_id: str,
    client: Any,
    metadata: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Report session start to the Anthropic session ingress endpoint.

    Args:
        session_id: The session identifier
        client: Anthropic API client
        metadata: Optional metadata to include

    Returns:
        True if reported successfully.
    """
    try:
        import httpx
        from ...utils.auth import get_api_key, get_base_url
        import platform
        import sys

        api_key = get_api_key()
        if not api_key:
            return False

        base_url = get_base_url() or 'https://api.anthropic.com'

        payload: Dict[str, Any] = {
            'sessionId': session_id,
            'platform': sys.platform,
            'timestamp': int(time.time() * 1000),
        }

        if metadata:
            payload.update(metadata)

        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.post(
                f"{base_url}{SESSION_INGRESS_ENDPOINT}",
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json=payload,
            )
            return response.status_code in (200, 201, 204)
    except Exception as e:
        logger.debug(f'Session ingress report failed: {e}')
        return False


async def report_session_end(
    session_id: str,
    client: Any,
    stats: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Report session end to the Anthropic session ingress endpoint.

    Args:
        session_id: The session identifier
        client: Anthropic API client
        stats: Optional session statistics

    Returns:
        True if reported successfully.
    """
    try:
        import httpx
        from ...utils.auth import get_api_key, get_base_url

        api_key = get_api_key()
        if not api_key:
            return False

        base_url = get_base_url() or 'https://api.anthropic.com'

        payload: Dict[str, Any] = {
            'sessionId': session_id,
            'event': 'end',
            'timestamp': int(time.time() * 1000),
        }

        if stats:
            payload['stats'] = stats

        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.post(
                f"{base_url}{SESSION_INGRESS_ENDPOINT}",
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json=payload,
            )
            return response.status_code in (200, 201, 204)
    except Exception as e:
        logger.debug(f'Session end report failed: {e}')
        return False

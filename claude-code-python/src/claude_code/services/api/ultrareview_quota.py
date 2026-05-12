"""
ultrareview_quota.py - Ultra-review quota management.

Port of TypeScript ultrareviewQuota.ts.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ULTRAREVIEW_QUOTA_ENDPOINT = '/api/claude_code/ultrareview_quota'


async def get_ultrareview_quota(client: Any) -> Dict[str, Any]:
    """
    Get the user's ultra-review quota.

    Args:
        client: Anthropic API client

    Returns:
        Dict with 'remaining', 'total', 'resetAt' keys.
    """
    try:
        import httpx
        from ...utils.auth import get_api_key, get_base_url

        api_key = get_api_key()
        if not api_key:
            return {'remaining': 0, 'total': 0, 'resetAt': None}

        base_url = get_base_url() or 'https://api.anthropic.com'

        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.get(
                f"{base_url}{ULTRAREVIEW_QUOTA_ENDPOINT}",
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                },
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    'remaining': data.get('remaining', 0),
                    'total': data.get('total', 0),
                    'resetAt': data.get('resetAt'),
                }

        return {'remaining': 0, 'total': 0, 'resetAt': None}
    except Exception as e:
        logger.debug(f'Ultra-review quota fetch failed: {e}')
        return {'remaining': 0, 'total': 0, 'resetAt': None}


def is_ultrareview_enabled() -> bool:
    """Check if ultra-review is enabled for the current session."""
    return bool(os.environ.get('CLAUDE_CODE_ULTRAREVIEW', '').lower() in ('1', 'true'))


async def check_and_decrement_ultrareview_quota(
    client: Any,
) -> Dict[str, Any]:
    """
    Check and decrement the ultra-review quota.

    Args:
        client: Anthropic API client

    Returns:
        Dict with 'allowed' bool and 'quotaInfo'.
    """
    quota = await get_ultrareview_quota(client)

    if quota.get('remaining', 0) <= 0:
        return {'allowed': False, 'quotaInfo': quota}

    return {'allowed': True, 'quotaInfo': quota}

"""
referral.py - Referral program utilities.

Port of TypeScript referral.ts.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

REFERRAL_ENDPOINT = '/api/claude_code/referral'


async def get_referral_info(client: Any) -> Optional[Dict[str, Any]]:
    """
    Get referral program information for the current user.

    Args:
        client: Anthropic API client

    Returns:
        Referral info dict with 'code', 'url', 'credits', or None if unavailable.
    """
    try:
        import httpx
        from ...utils.auth import get_api_key, get_base_url

        api_key = get_api_key()
        if not api_key:
            return None

        base_url = get_base_url() or 'https://api.anthropic.com'

        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.get(
                f"{base_url}{REFERRAL_ENDPOINT}",
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                },
            )

            if response.status_code == 200:
                return response.json()

        return None
    except Exception as e:
        logger.debug(f'Referral info fetch failed: {e}')
        return None


async def apply_referral_code(
    client: Any,
    referral_code: str,
) -> Dict[str, Any]:
    """
    Apply a referral code for the current user.

    Args:
        client: Anthropic API client
        referral_code: The referral code to apply

    Returns:
        Result dict with 'success' bool and optional 'message'.
    """
    try:
        import httpx
        from ...utils.auth import get_api_key, get_base_url

        api_key = get_api_key()
        if not api_key:
            return {'success': False, 'message': 'No API key configured'}

        base_url = get_base_url() or 'https://api.anthropic.com'

        async with httpx.AsyncClient(timeout=5.0) as http:
            response = await http.post(
                f"{base_url}{REFERRAL_ENDPOINT}/apply",
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
                json={'code': referral_code},
            )

            if response.status_code == 200:
                return {'success': True, **response.json()}
            else:
                return {
                    'success': False,
                    'message': f'Server returned {response.status_code}',
                }
    except Exception as e:
        logger.debug(f'Referral code apply failed: {e}')
        return {'success': False, 'message': str(e)}


def get_referral_code_from_env() -> Optional[str]:
    """Get referral code from environment variable."""
    return os.environ.get('CLAUDE_CODE_REFERRAL_CODE') or None

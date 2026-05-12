"""
overage_credit_grant.py - Handle overage credit grant flow.

Port of TypeScript overageCreditGrant.ts.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

OVERAGE_ENDPOINT = '/api/claude_code/overage_credit_grant'


async def check_overage_credit_grant_eligibility(client: Any) -> Dict[str, Any]:
    """
    Check if the user is eligible for an overage credit grant.

    Args:
        client: Anthropic API client

    Returns:
        Dict with 'eligible' bool and 'amount' if eligible.
    """
    try:
        import httpx
        from ...utils.auth import get_api_key, get_base_url

        api_key = get_api_key()
        if not api_key:
            return {'eligible': False}

        base_url = get_base_url() or 'https://api.anthropic.com'

        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(
                f"{base_url}{OVERAGE_ENDPOINT}/check",
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                },
            )

            if response.status_code == 200:
                return response.json()

        return {'eligible': False}
    except Exception as e:
        logger.debug(f'Overage credit grant check failed: {e}')
        return {'eligible': False}


async def accept_overage_credit_grant(client: Any) -> bool:
    """
    Accept an overage credit grant.

    Args:
        client: Anthropic API client

    Returns:
        True if accepted successfully.
    """
    try:
        import httpx
        from ...utils.auth import get_api_key, get_base_url

        api_key = get_api_key()
        if not api_key:
            return False

        base_url = get_base_url() or 'https://api.anthropic.com'

        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.post(
                f"{base_url}{OVERAGE_ENDPOINT}/accept",
                headers={
                    'x-api-key': api_key,
                    'anthropic-version': '2023-06-01',
                    'content-type': 'application/json',
                },
            )
            return response.status_code == 200
    except Exception as e:
        logger.debug(f'Overage credit grant accept failed: {e}')
        return False

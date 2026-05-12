"""
grove.py - Grove (Anthropic internal) API client utilities.

Port of TypeScript grove.ts.
"""

import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

GROVE_API_BASE_URL = 'https://grove.corp.anthropic.com'


def is_grove_environment() -> bool:
    """Check if we're running in the Grove environment."""
    return bool(
        os.environ.get('ANTHROPIC_GROVE_ENVIRONMENT')
        or os.environ.get('ANTHROPIC_GROVE_API_URL')
        or os.environ.get('USER_TYPE') == 'ant'
    )


def get_grove_api_url() -> str:
    """Get the Grove API base URL."""
    return os.environ.get('ANTHROPIC_GROVE_API_URL', GROVE_API_BASE_URL)


async def get_grove_feature_flags() -> Dict[str, Any]:
    """
    Fetch feature flags from Grove.

    Returns:
        Dict of feature flags, empty on error.
    """
    if not is_grove_environment():
        return {}

    try:
        import httpx
        from ...utils.auth import get_auth_headers

        auth = get_auth_headers()
        if auth.get('error'):
            return {}

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{get_grove_api_url()}/api/v1/feature-flags",
                headers=auth.get('headers', {}),
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.debug(f'Grove feature flags fetch failed: {e}')
        return {}


async def get_grove_dynamic_config(
    config_key: str,
    default_value: Optional[Any] = None,
) -> Any:
    """
    Fetch dynamic configuration from Grove.

    Args:
        config_key: The configuration key to fetch
        default_value: Default value if fetch fails

    Returns:
        Configuration value or default.
    """
    if not is_grove_environment():
        return default_value

    try:
        import httpx
        from ...utils.auth import get_auth_headers

        auth = get_auth_headers()
        if auth.get('error'):
            return default_value

        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{get_grove_api_url()}/api/v1/config/{config_key}",
                headers=auth.get('headers', {}),
            )
            response.raise_for_status()
            return response.json()
    except Exception as e:
        logger.debug(f'Grove config fetch failed for {config_key}: {e}')
        return default_value

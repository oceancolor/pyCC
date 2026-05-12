"""
hunyuan.py - Hunyuan API provider support.

Port of TypeScript hunyuan.ts.
"""

import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

HUNYUAN_BASE_URL = 'https://api.hunyuan.cloud.tencent.com/v1'
HUNYUAN_MODEL_MAPPING = {
    'claude-3-5-sonnet-20241022': 'hunyuan-standard',
    'claude-3-opus-20240229': 'hunyuan-pro',
    'claude-3-haiku-20240307': 'hunyuan-lite',
}


def is_hunyuan_enabled() -> bool:
    """Check if Hunyuan API provider is enabled."""
    return bool(
        os.environ.get('HUNYUAN_API_KEY')
        or os.environ.get('HUNYUAN_SECRET_KEY')
    )


def get_hunyuan_client_options() -> Optional[Dict[str, Any]]:
    """
    Get Hunyuan API client options.

    Returns:
        Dict with 'apiKey', 'baseURL', and other options, or None.
    """
    api_key = os.environ.get('HUNYUAN_API_KEY')
    secret_key = os.environ.get('HUNYUAN_SECRET_KEY')
    secret_id = os.environ.get('HUNYUAN_SECRET_ID')

    if not api_key and not secret_key:
        return None

    base_url = os.environ.get('HUNYUAN_BASE_URL', HUNYUAN_BASE_URL)

    if api_key:
        return {
            'apiKey': api_key,
            'baseURL': base_url,
            'defaultHeaders': {
                'Authorization': f"Bearer {api_key}",
            },
        }

    if secret_key and secret_id:
        # Tencent Cloud signature-based auth
        return {
            'apiKey': secret_key,
            'baseURL': base_url,
            'defaultHeaders': {
                'X-TC-SecretId': secret_id,
            },
        }

    return None


def map_model_to_hunyuan(model_name: str) -> str:
    """
    Map an Anthropic model name to a Hunyuan model name.

    Args:
        model_name: Anthropic model name

    Returns:
        Hunyuan model name, or original if no mapping.
    """
    return HUNYUAN_MODEL_MAPPING.get(model_name, model_name)


def transform_request_for_hunyuan(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform an Anthropic API request for Hunyuan compatibility.

    Args:
        request: Anthropic-format request dict

    Returns:
        Hunyuan-compatible request dict.
    """
    transformed = dict(request)

    # Map model name
    if 'model' in transformed:
        transformed['model'] = map_model_to_hunyuan(transformed['model'])

    # Convert messages format if needed
    messages = transformed.get('messages', [])
    if messages:
        converted = []
        for msg in messages:
            if isinstance(msg, dict):
                content = msg.get('content')
                if isinstance(content, list):
                    # Flatten content blocks to text
                    text_parts = [
                        block.get('text', '')
                        for block in content
                        if isinstance(block, dict) and block.get('type') == 'text'
                    ]
                    converted.append({
                        'role': msg.get('role', 'user'),
                        'content': '\n'.join(text_parts),
                    })
                else:
                    converted.append(msg)
            else:
                converted.append(msg)
        transformed['messages'] = converted

    return transformed

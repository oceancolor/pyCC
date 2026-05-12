"""
prompt_cache_break_detection.py - Detect unintended prompt cache breaks.

Port of TypeScript promptCacheBreakDetection.ts.
"""

import hashlib
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Cache for prompt hashes to detect changes
_last_system_hash: Optional[str] = None
_last_tools_hash: Optional[str] = None


def _hash_content(content: Any) -> str:
    """Hash content for change detection."""
    import json
    try:
        serialized = json.dumps(content, sort_keys=True, ensure_ascii=False, default=str)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]
    except Exception:
        return 'error'


def check_prompt_cache_break(request_params: Dict[str, Any]) -> Optional[str]:
    """
    Check if the request will cause a prompt cache break.

    A cache break occurs when system prompt or tools change between requests,
    or when cache control markers are missing/incorrect.

    Args:
        request_params: The API request parameters dict

    Returns:
        Warning message if a cache break is detected, None otherwise.
    """
    global _last_system_hash, _last_tools_hash

    system = request_params.get('system')
    tools = request_params.get('tools')

    warnings = []

    # Check system prompt changes
    system_hash = _hash_content(system) if system is not None else None
    if _last_system_hash is not None and system_hash != _last_system_hash:
        warnings.append('System prompt changed — cache break detected')
    _last_system_hash = system_hash

    # Check tools changes
    tools_hash = _hash_content(tools) if tools is not None else None
    if _last_tools_hash is not None and tools_hash != _last_tools_hash:
        warnings.append('Tools changed — cache break detected')
    _last_tools_hash = tools_hash

    return '; '.join(warnings) if warnings else None


def reset_prompt_cache_break_detection() -> None:
    """Reset the detection state (call between sessions)."""
    global _last_system_hash, _last_tools_hash
    _last_system_hash = None
    _last_tools_hash = None


def has_cache_control(
    content: Any,
    expected_type: str = 'ephemeral',
) -> bool:
    """
    Check if content has the expected cache_control marker.

    Args:
        content: Content to check (string or list of blocks)
        expected_type: Expected cache control type

    Returns:
        True if the cache control marker is present.
    """
    if isinstance(content, str):
        return False

    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict):
                cache_control = block.get('cache_control', {})
                if isinstance(cache_control, dict):
                    if cache_control.get('type') == expected_type:
                        return True

    return False


def add_cache_control(
    content: List[Any],
    cache_type: str = 'ephemeral',
) -> List[Any]:
    """
    Add cache control markers to the last block of content.

    Args:
        content: List of content blocks
        cache_type: Cache control type

    Returns:
        Modified content list.
    """
    if not content:
        return content

    result = list(content)
    last_block = result[-1]

    if isinstance(last_block, dict):
        result[-1] = {
            **last_block,
            'cache_control': {'type': cache_type},
        }

    return result

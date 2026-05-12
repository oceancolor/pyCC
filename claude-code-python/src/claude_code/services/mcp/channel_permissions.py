"""
channel_permissions.py - Permission prompts over channels (Telegram, iMessage, Discord).

Port of TypeScript channelPermissions.ts.
"""

import hashlib
import json
import re
from typing import Any, Callable, Dict, List, Optional


def is_channel_permission_relay_enabled() -> bool:
    """Check if channel permission relay is enabled."""
    try:
        from ...services.analytics.growthbook import get_feature_value_cached_may_be_stale
        return get_feature_value_cached_may_be_stale('tengu_harbor_permissions', False)
    except ImportError:
        return False


# Permission reply regex: accepts "yes/no XXXXX" format
PERMISSION_REPLY_RE = re.compile(
    r'^\s*(y|yes|n|no)\s+([a-km-z]{5})\s*$',
    re.IGNORECASE,
)

# ID alphabet: a-z minus 'l' (looks like 1/I)
_ID_ALPHABET = 'abcdefghijkmnopqrstuvwxyz'

# Substring blocklist for generated IDs
_ID_AVOID_SUBSTRINGS = [
    'fuck', 'shit', 'cunt', 'cock', 'dick', 'twat', 'piss', 'crap',
    'bitch', 'whore', 'ass', 'tit', 'cum', 'fag', 'dyke', 'nig',
    'kike', 'rape', 'nazi', 'damn', 'poo', 'pee', 'wank', 'anus',
]


def _fnv1a_32(data: str) -> int:
    """FNV-1a 32-bit hash."""
    h = 0x811c9dc5
    for char in data:
        h ^= ord(char)
        h = (h * 0x01000193) & 0xFFFFFFFF
    return h


def _hash_to_id(input_str: str) -> str:
    """Hash to 5-letter ID using FNV-1a."""
    h = _fnv1a_32(input_str)
    result = ''
    for _ in range(5):
        result += _ID_ALPHABET[h % 25]
        h //= 25
    return result


def short_request_id(tool_use_id: str) -> str:
    """
    Generate a short 5-letter ID from a toolUseID.
    Re-hashes with a salt if result contains blocked substrings.
    """
    candidate = _hash_to_id(tool_use_id)
    for salt in range(10):
        if not any(bad in candidate for bad in _ID_AVOID_SUBSTRINGS):
            return candidate
        candidate = _hash_to_id(f"{tool_use_id}:{salt}")
    return candidate


def truncate_for_preview(input_data: Any) -> str:
    """Truncate tool input to a phone-sized JSON preview (200 chars)."""
    try:
        s = json.dumps(input_data, ensure_ascii=False)
        return s[:200] + '…' if len(s) > 200 else s
    except Exception:
        return '(unserializable)'


class ChannelPermissionResponse:
    """Response from a channel permission relay."""
    def __init__(self, behavior: str, from_server: str):
        self.behavior = behavior  # 'allow' | 'deny'
        self.from_server = from_server


class ChannelPermissionCallbacks:
    """Callbacks for channel permission relay."""

    def __init__(self):
        self._pending: Dict[str, Callable[[ChannelPermissionResponse], None]] = {}

    def on_response(
        self,
        request_id: str,
        handler: Callable[[ChannelPermissionResponse], None],
    ) -> Callable[[], None]:
        """Register a resolver for a request ID. Returns unsubscribe."""
        key = request_id.lower()
        self._pending[key] = handler

        def unsubscribe() -> None:
            self._pending.pop(key, None)

        return unsubscribe

    def resolve(
        self,
        request_id: str,
        behavior: str,
        from_server: str,
    ) -> bool:
        """Resolve a pending request. Returns True if the ID was pending."""
        key = request_id.lower()
        resolver = self._pending.get(key)
        if not resolver:
            return False

        del self._pending[key]
        resolver(ChannelPermissionResponse(behavior=behavior, from_server=from_server))
        return True


def create_channel_permission_callbacks() -> ChannelPermissionCallbacks:
    """Factory for the callbacks object."""
    return ChannelPermissionCallbacks()


def filter_permission_relay_clients(
    clients: List[Dict[str, Any]],
    is_in_allowlist: Callable[[str], bool],
) -> List[Dict[str, Any]]:
    """
    Filter MCP clients down to those that can relay permission prompts.
    """
    return [
        c for c in clients
        if (c.get('type') == 'connected'
            and is_in_allowlist(c.get('name', ''))
            and (c.get('capabilities') or {}).get('experimental', {}).get('claude/channel') is not None
            and (c.get('capabilities') or {}).get('experimental', {}).get('claude/channel/permission') is not None)
    ]

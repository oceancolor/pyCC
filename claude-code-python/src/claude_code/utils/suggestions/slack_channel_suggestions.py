"""Slack channel suggestions for the @ mention completion. Ported from utils/suggestions/slackChannelSuggestions.ts"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Optional

_CACHE_TTL_MS = 5 * 60 * 1000  # 5 minutes

@dataclass
class SlackChannel:
    """A Slack channel descriptor."""

    id: str
    name: str
    is_member: bool = False
    num_members: int = 0
    topic: Optional[str] = None


_channels_cache: Optional[List[SlackChannel]] = None
_channels_cache_timestamp: float = 0.0


def clear_slack_channels_cache() -> None:
    """Invalidate the cached channel list."""
    global _channels_cache, _channels_cache_timestamp
    _channels_cache = None
    _channels_cache_timestamp = 0.0


async def get_slack_channels(slack_token: Optional[str] = None) -> List[SlackChannel]:
    """Fetch the list of joinable Slack channels for the authed workspace.

    Results are cached for ``_CACHE_TTL_MS`` milliseconds to avoid hammering
    the Slack API on every keystroke.

    Args:
        slack_token: A ``xoxp-…`` or ``xoxb-…`` Slack OAuth token.
            If None the function checks the ``SLACK_BOT_TOKEN`` environment variable.

    Returns:
        A list of :class:`SlackChannel` objects, or an empty list on failure.
    """
    import os
    import asyncio

    global _channels_cache, _channels_cache_timestamp

    now_ms = time.time() * 1000
    if _channels_cache is not None and now_ms - _channels_cache_timestamp < _CACHE_TTL_MS:
        return _channels_cache

    token = slack_token or os.environ.get("SLACK_BOT_TOKEN") or os.environ.get("SLACK_TOKEN")
    if not token:
        return []

    try:
        import aiohttp  # type: ignore[import]
    except ImportError:
        return []

    channels: List[SlackChannel] = []
    cursor: Optional[str] = None

    async with aiohttp.ClientSession() as session:
        while True:
            params: dict = {
                "token": token,
                "limit": "200",
                "types": "public_channel,private_channel",
                "exclude_archived": "true",
            }
            if cursor:
                params["cursor"] = cursor

            try:
                async with session.get(
                    "https://slack.com/api/conversations.list",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    data = await resp.json()
            except Exception:
                break

            if not data.get("ok"):
                break

            for ch in data.get("channels", []):
                channels.append(
                    SlackChannel(
                        id=ch.get("id", ""),
                        name=ch.get("name", ""),
                        is_member=ch.get("is_member", False),
                        num_members=ch.get("num_members", 0),
                        topic=ch.get("topic", {}).get("value") or None,
                    )
                )

            next_cursor = data.get("response_metadata", {}).get("next_cursor")
            if not next_cursor:
                break
            cursor = next_cursor

    _channels_cache = channels
    _channels_cache_timestamp = time.time() * 1000
    return channels


def search_slack_channels(query: str, channels: List[SlackChannel], max_results: int = 10) -> List[SlackChannel]:
    """Filter channels by a prefix query (case-insensitive).

    Args:
        query: The partial channel name the user has typed.
        channels: The full list of channels to search.
        max_results: Maximum number of results.

    Returns:
        A filtered and sorted list of matching channels.
    """
    q = query.lstrip("#").lower()
    if not q:
        return channels[:max_results]

    matched = [ch for ch in channels if ch.name.lower().startswith(q)]
    matched.sort(key=lambda ch: (not ch.is_member, ch.name))
    return matched[:max_results]

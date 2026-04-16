"""Collapse consecutive completed background bash notifications.

Ported from collapseBackgroundBashNotifications.ts — merges runs of
completed background-bash task notifications into a single synthetic
"N background commands completed" message.
"""

from typing import Any

# XML tag names (mirrors constants/xml.ts)
STATUS_TAG = 'status'
SUMMARY_TAG = 'summary'
TASK_NOTIFICATION_TAG = 'task_notification'

# Prefix that distinguishes bash-kind LocalShellTask completions
BACKGROUND_BASH_SUMMARY_PREFIX = 'Background bash'


def _extract_tag(text: str, tag: str) -> str | None:
    """Extract inner text of the first occurrence of <tag>...</tag>."""
    import re
    m = re.search(rf'<{re.escape(tag)}>(.*?)</{re.escape(tag)}>', text, re.DOTALL)
    return m.group(1) if m else None


def _is_completed_background_bash(msg: Any) -> bool:
    """Return True if *msg* is a successfully completed background-bash notification."""
    if not isinstance(msg, dict):
        return False
    if msg.get('type') != 'user':
        return False
    content = msg.get('message', {}).get('content', [])
    if not content:
        return False
    first = content[0]
    if not isinstance(first, dict) or first.get('type') != 'text':
        return False
    text: str = first.get('text', '')
    if f'<{TASK_NOTIFICATION_TAG}' not in text:
        return False
    if _extract_tag(text, STATUS_TAG) != 'completed':
        return False
    summary = _extract_tag(text, SUMMARY_TAG) or ''
    return summary.startswith(BACKGROUND_BASH_SUMMARY_PREFIX)


def _make_collapsed_message(proto: dict, count: int) -> dict:
    """Build a synthetic task-notification dict for *count* completions."""
    import copy
    synthetic = copy.deepcopy(proto)
    text = (
        f'<{TASK_NOTIFICATION_TAG}>'
        f'<{STATUS_TAG}>completed</{STATUS_TAG}>'
        f'<{SUMMARY_TAG}>{count} background commands completed</{SUMMARY_TAG}>'
        f'</{TASK_NOTIFICATION_TAG}>'
    )
    synthetic['message'] = {
        'role': 'user',
        'content': [{'type': 'text', 'text': text}],
    }
    return synthetic


def collapse_background_bash_notifications(
    messages: list[Any],
    verbose: bool,
    fullscreen_enabled: bool = True,
) -> list[Any]:
    """Collapse consecutive completed-background-bash notifications.

    Args:
        messages: List of renderable message dicts.
        verbose: If True, pass through unchanged (ctrl+O mode).
        fullscreen_enabled: Whether fullscreen env is active. Pass-through
            when False (mirrors isFullscreenEnvEnabled() check).
    """
    if not fullscreen_enabled:
        return messages
    if verbose:
        return messages

    result: list[Any] = []
    i = 0
    while i < len(messages):
        msg = messages[i]
        if _is_completed_background_bash(msg):
            count = 0
            start_msg = msg
            while i < len(messages) and _is_completed_background_bash(messages[i]):
                count += 1
                i += 1
            if count == 1:
                result.append(start_msg)
            else:
                result.append(_make_collapsed_message(start_msg, count))
        else:
            result.append(msg)
            i += 1
    return result

"""Session title generation - Python port of sessionTitle.ts.

The original calls Haiku (Claude-3-Haiku) to generate a concise session title.
This port provides the same interface with a lightweight local fallback that
extracts the first meaningful user message and truncates it.
"""

from __future__ import annotations

import re
from typing import Any, Optional

MAX_CONVERSATION_TEXT = 1000
MAX_TITLE_CHARS = 50
_WHITESPACE_RE = re.compile(r'\s+')


def extract_conversation_text(messages: list[dict[str, Any]]) -> str:
    """Flatten messages into a single string for title generation.

    Skips meta / non-human-origin messages; tail-slices to last 1000 chars.
    """
    parts: list[str] = []
    for msg in messages:
        msg_type = msg.get('type')
        if msg_type not in ('user', 'assistant'):
            continue
        if msg.get('isMeta'):
            continue
        origin = msg.get('origin')
        if origin and isinstance(origin, dict) and origin.get('kind') != 'human':
            continue
        content = msg.get('message', {}).get('content', '') if 'message' in msg else msg.get('content', '')
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get('type') == 'text':
                    text = block.get('text', '')
                    if text:
                        parts.append(str(text))

    text = '\n'.join(parts)
    return text[-MAX_CONVERSATION_TEXT:] if len(text) > MAX_CONVERSATION_TEXT else text


def _truncate_to_title(text: str, max_chars: int = MAX_TITLE_CHARS) -> str:
    """Collapse whitespace and truncate to max_chars, appending '…' if cut."""
    collapsed = _WHITESPACE_RE.sub(' ', text).strip()
    if len(collapsed) <= max_chars:
        return collapsed
    return collapsed[:max_chars].rstrip() + '…'


def generate_session_title(
    messages: list[dict[str, Any]],
    *,
    max_chars: int = MAX_TITLE_CHARS,
) -> Optional[str]:
    """Generate a concise session title from the conversation messages.

    Extracts the first user message text and truncates to *max_chars*.
    Returns None if no suitable content is found.

    In production Claude Code this calls Haiku for an AI-generated title;
    this port uses a deterministic local approach to avoid the API dependency.
    """
    conversation_text = extract_conversation_text(messages)
    if not conversation_text.strip():
        return None

    # Use only the first line / sentence for the title
    first_line = conversation_text.strip().splitlines()[0]
    title = _truncate_to_title(first_line, max_chars)
    return title if title else None


def generate_session_title_from_description(
    description: str,
    *,
    max_chars: int = MAX_TITLE_CHARS,
) -> Optional[str]:
    """Generate a title from a plain description string (first user message)."""
    trimmed = description.strip()
    if not trimmed:
        return None
    return _truncate_to_title(trimmed, max_chars)

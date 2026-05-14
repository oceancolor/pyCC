"""Direct member message helpers. Ported from directMemberMessage.ts.

Parses ``@agent-name message`` syntax for direct team-member messaging and
sends messages to a specific swarm teammate, bypassing the model.
"""
from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Literal, Optional, Union

__all__ = [
    "parse_direct_member_message",
    "send_direct_member_message",
    "DirectMessageResult",
    "format_mention",
]

# Match "@name message" where name is word-chars and hyphens
_DIRECT_MSG_RE = re.compile(r"^@([\w-]+)\s+(.+)$", re.DOTALL)


def parse_direct_member_message(
    input_text: str,
) -> Optional[dict[str, str]]:
    """Parse ``@agent-name message`` syntax.

    Returns ``{"recipientName": str, "message": str}`` or None if the
    input does not match the pattern.
    """
    match = _DIRECT_MSG_RE.match(input_text)
    if not match:
        return None

    recipient_name, message = match.group(1), match.group(2)
    if not recipient_name or not message:
        return None

    trimmed = message.strip()
    if not trimmed:
        return None

    return {"recipientName": recipient_name, "message": trimmed}


# Type alias for the result of send_direct_member_message
DirectMessageResult = Union[
    dict[Literal["success"], Literal[True]],
    dict,
]

WriteToMailboxFn = Callable[
    [str, dict[str, str], str],
    Awaitable[None],
]


async def send_direct_member_message(
    recipient_name: str,
    message: str,
    team_context: Optional[Any],
    write_to_mailbox: Optional[WriteToMailboxFn] = None,
) -> DirectMessageResult:
    """Send a direct message to a swarm team member.

    Returns a result dict with ``success=True`` on success, or
    ``success=False`` with an ``error`` key on failure.
    """
    if not team_context or not write_to_mailbox:
        return {"success": False, "error": "no_team_context"}

    teammates = getattr(team_context, "teammates", None) or {}
    member = next(
        (t for t in teammates.values() if getattr(t, "name", None) == recipient_name),
        None,
    )

    if member is None:
        return {
            "success": False,
            "error": "unknown_recipient",
            "recipientName": recipient_name,
        }

    import datetime

    team_name = getattr(team_context, "team_name", "")
    await write_to_mailbox(
        recipient_name,
        {
            "from": "user",
            "text": message,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        },
        team_name,
    )

    return {"success": True, "recipientName": recipient_name}


def format_mention(name: str) -> str:
    """Format a team member name as a @mention string."""
    return f"@{name}"

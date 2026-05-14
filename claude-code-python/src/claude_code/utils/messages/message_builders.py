"""Message builder utilities. Ported from utils/messages/."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

# XML tag constants (mirrors src/constants/xml.ts)
LOCAL_COMMAND_STDOUT_TAG = "output"
LOCAL_COMMAND_STDERR_TAG = "stderr"


def create_assistant_message(
    content: Any,
    uuid: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict:
    """Build an assistant message dict.

    Args:
        content: Message content (string or list of content blocks).
        uuid: Optional UUID. Auto-generated if not provided.
        timestamp: Optional ISO timestamp. Uses current time if not provided.

    Returns:
        A dict matching the internal ``AssistantMessage`` shape.
    """
    import uuid as uuid_mod
    from datetime import datetime, timezone

    return {
        "type": "assistant",
        "message": {"role": "assistant", "content": content},
        "uuid": uuid or str(uuid_mod.uuid4()),
        "requestId": None,
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }


def create_user_message(
    content: Any,
    uuid: Optional[str] = None,
    timestamp: Optional[str] = None,
    is_meta: bool = False,
) -> dict:
    """Build a user message dict."""
    import uuid as uuid_mod
    from datetime import datetime, timezone

    return {
        "type": "user",
        "message": {"role": "user", "content": content},
        "uuid": uuid or str(uuid_mod.uuid4()),
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
        "isMeta": is_meta,
    }


def create_system_message(
    content: str,
    level: str = "info",
    uuid: Optional[str] = None,
    timestamp: Optional[str] = None,
) -> dict:
    """Build a system message dict."""
    import uuid as uuid_mod
    from datetime import datetime, timezone

    return {
        "type": "system",
        "content": content,
        "level": level,
        "uuid": uuid or str(uuid_mod.uuid4()),
        "timestamp": timestamp or datetime.now(timezone.utc).isoformat(),
    }


def build_local_command_output_blocks(stdout: str, stderr: str) -> List[dict]:
    """Build XML-tagged content blocks for local command output.

    Args:
        stdout: Standard output text.
        stderr: Standard error text.

    Returns:
        A list of content block dicts for inclusion in a user message.
    """
    blocks = []
    if stdout:
        blocks.append(
            {
                "type": "text",
                "text": f"<{LOCAL_COMMAND_STDOUT_TAG}>\n{stdout}\n</{LOCAL_COMMAND_STDOUT_TAG}>",
            }
        )
    if stderr:
        blocks.append(
            {
                "type": "text",
                "text": f"<{LOCAL_COMMAND_STDERR_TAG}>\n{stderr}\n</{LOCAL_COMMAND_STDERR_TAG}>",
            }
        )
    return blocks


def strip_ansi(text: str) -> str:
    """Remove ANSI escape codes from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*[mGKHF]|\x1b[()][AB012]|\x1b[@-Z\\-_]')
    return ansi_escape.sub("", text)

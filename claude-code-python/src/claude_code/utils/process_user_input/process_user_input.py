"""Top-level user input processing. Ported from utils/processUserInput/processUserInput.ts"""

from __future__ import annotations

import re
import uuid as uuid_module
from typing import Any, Dict, List, Optional, Union

from .process_text_prompt import process_text_prompt


def _process_slash_command(
    input_text: str,
    context: dict,
) -> Optional[dict]:
    """Try to parse and handle a slash command.

    Returns a result dict if the command was handled, or None to fall through
    to normal text processing.
    """
    if not input_text.strip().startswith("/"):
        return None

    # Simple stub: return a "command not found" system message
    try:
        from claude_code.utils.messages.message_builders import create_system_message

        cmd_name = input_text.strip().split()[0]
        return {
            "messages": [
                create_system_message(
                    f"Command {cmd_name!r} not recognised (Python port).",
                    level="warning",
                )
            ],
            "shouldQuery": False,
        }
    except Exception:
        return None


async def process_user_input(
    input_text: Union[str, List[Dict[str, Any]]],
    pasted_contents: Optional[List[dict]] = None,
    context: Optional[dict] = None,
    msg_uuid: Optional[str] = None,
    permission_mode: Optional[str] = None,
    is_meta: bool = False,
) -> Dict[str, Any]:
    """Process user input and produce a list of messages and metadata.

    This is the main entry point for converting raw user input into the
    message objects that are sent to the Claude API.

    Args:
        input_text: The user's raw text input (string or content-block list).
        pasted_contents: Optional list of pasted images/files (PastedContent).
        context: Optional context dict (ToolUseContext/LocalJSXCommandContext).
        msg_uuid: Optional UUID for the generated user message.
        permission_mode: Current permission mode.
        is_meta: Whether the message is an internal meta-message.

    Returns:
        A dict with:
        - ``messages``: List of message dicts
        - ``shouldQuery``: Whether to send a query to Claude
        - ``model`` (optional): Override model string
        - ``effort`` (optional): Override effort value
        - ``resultText`` (optional): Output text for non-interactive mode
    """
    ctx = context or {}

    raw_text = input_text if isinstance(input_text, str) else ""

    # ---- Check for ultraplan keyword ---- #
    if isinstance(input_text, str) and _has_ultraplan_keyword(input_text):
        input_text = _replace_ultraplan_keyword(input_text)

    # ---- Slash commands ---- #
    if isinstance(input_text, str):
        slash_result = _process_slash_command(input_text, ctx)
        if slash_result is not None:
            return slash_result

    # ---- Collect image content blocks from pasted contents ---- #
    image_blocks: List[dict] = []
    image_paste_ids: List[int] = []
    attachment_messages: List[dict] = []

    for pasted in (pasted_contents or []):
        if pasted.get("type") == "image":
            paste_id = pasted.get("id", 0)
            media_type = pasted.get("mediaType", "image/png")
            b64_data = pasted.get("content", "")
            image_blocks.append(
                {
                    "type": "image",
                    "source": {"type": "base64", "media_type": media_type, "data": b64_data},
                }
            )
            image_paste_ids.append(paste_id)

    # ---- Delegate to processTextPrompt ---- #
    result = process_text_prompt(
        input_text=input_text,
        image_content_blocks=image_blocks,
        image_paste_ids=image_paste_ids,
        attachment_messages=attachment_messages,
        msg_uuid=msg_uuid,
        permission_mode=permission_mode,
        is_meta=is_meta,
    )
    return result


def _has_ultraplan_keyword(text: str) -> bool:
    """Return True if the text contains an 'ultraplan' trigger keyword."""
    try:
        from claude_code.utils.ultraplan.keyword import has_ultraplan_keyword

        return has_ultraplan_keyword(text)
    except Exception:
        return bool(re.search(r'\bultraplan\b', text, re.IGNORECASE))


def _replace_ultraplan_keyword(text: str) -> str:
    """Replace 'ultraplan' with 'plan' in the text."""
    try:
        from claude_code.utils.ultraplan.keyword import replace_ultraplan_keyword

        return replace_ultraplan_keyword(text)
    except Exception:
        return re.sub(r'\bultraplan\b', 'plan', text, flags=re.IGNORECASE)

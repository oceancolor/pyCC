"""Text prompt processing. Ported from utils/processUserInput/processTextPrompt.ts"""

from __future__ import annotations

import uuid as uuid_module
from typing import Any, Dict, List, Optional, Union


def _matches_negative_keyword(text: str) -> bool:
    """Return True if the prompt expresses clear refusal."""
    lower = text.lower().strip()
    negative_phrases = [
        "no", "stop", "cancel", "abort", "exit", "quit", "nevermind",
        "never mind", "forget it", "don't", "do not", "not now",
    ]
    return any(lower == phrase or lower.startswith(phrase + " ") for phrase in negative_phrases)


def _matches_keep_going_keyword(text: str) -> bool:
    """Return True if the prompt asks the model to continue."""
    lower = text.lower().strip()
    keep_going = [
        "keep going", "continue", "proceed", "go on", "carry on",
        "go ahead", "go", "ok", "okay",
    ]
    return any(lower == phrase or lower.startswith(phrase + " ") for phrase in keep_going)


def process_text_prompt(
    input_text: Union[str, List[Dict[str, Any]]],
    image_content_blocks: List[Dict[str, Any]],
    image_paste_ids: List[int],
    attachment_messages: Optional[List[Dict[str, Any]]] = None,
    msg_uuid: Optional[str] = None,
    permission_mode: Optional[str] = None,
    is_meta: bool = False,
) -> Dict[str, Any]:
    """Process a user text prompt and build a list of messages.

    Args:
        input_text: The user's raw input (string or list of content blocks).
        image_content_blocks: List of base64-encoded image content blocks
            to append to the message.
        image_paste_ids: List of paste IDs corresponding to pasted images.
        attachment_messages: Optional additional attachment/context messages.
        msg_uuid: Optional UUID for the user message. Auto-generated if None.
        permission_mode: The current permission mode (unused in Python port).
        is_meta: Whether this is an internal meta-message.

    Returns:
        A dict ``{"messages": [...], "shouldQuery": bool}``.
    """
    from claude_code.utils.messages.message_builders import create_user_message

    prompt_id = str(uuid_module.uuid4())

    # Extract the primary user-prompt text for keyword matching
    if isinstance(input_text, str):
        user_prompt_text = input_text
    else:
        user_prompt_text = next(
            (b.get("text", "") for b in input_text if isinstance(b, dict) and b.get("type") == "text"),
            "",
        )

    is_negative = _matches_negative_keyword(user_prompt_text)
    is_keep_going = _matches_keep_going_keyword(user_prompt_text)

    messages: List[Dict[str, Any]] = []

    # If we have pasted images, combine text + images into one user message
    if image_content_blocks:
        if isinstance(input_text, str):
            text_blocks = [{"type": "text", "text": input_text}] if input_text.strip() else []
        else:
            text_blocks = list(input_text)
        content = [*text_blocks, *image_content_blocks]
    else:
        content = input_text if not isinstance(input_text, str) else input_text

    user_msg = create_user_message(
        content=content,
        uuid=msg_uuid,
        is_meta=is_meta,
    )
    user_msg["promptId"] = prompt_id
    if image_paste_ids:
        user_msg["imagePasteIds"] = image_paste_ids
    messages.append(user_msg)

    # Append any attachment/context messages
    for attachment in (attachment_messages or []):
        messages.append(attachment)

    # shouldQuery = False only when the user explicitly says "no/stop"
    should_query = not is_negative

    return {"messages": messages, "shouldQuery": should_query}

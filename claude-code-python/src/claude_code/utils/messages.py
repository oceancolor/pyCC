"""
Message type definitions and utilities.
Original TS: src/utils/messages.ts (5512 lines) + src/types/message.ts (partial)

Ports all exported functions/constants. UI-only helpers (React streaming,
plan-mode instructions, attachment normalisation) are included as stubs or
minimal Python equivalents so that import-level resolution works.
"""
from __future__ import annotations

import re
import uuid as _uuid_mod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Literal, Optional, Set, Tuple, Union

from claude_code.constants.messages import NO_CONTENT_MESSAGE


# ---------------------------------------------------------------------------
# Message roles
# ---------------------------------------------------------------------------

MessageRole = Literal["user", "assistant"]


# ---------------------------------------------------------------------------
# Content block types (Anthropic SDK message content)
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    type: Literal["text"] = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    type: Literal["tool_use"] = "tool_use"
    id: str = ""
    name: str = ""
    input: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResultBlock:
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: str = ""
    content: Union[str, List[Any]] = ""
    is_error: Optional[bool] = None


@dataclass
class ThinkingBlock:
    type: Literal["thinking"] = "thinking"
    thinking: str = ""
    signature: str = ""


@dataclass
class RedactedThinkingBlock:
    type: Literal["redacted_thinking"] = "redacted_thinking"
    data: str = ""


@dataclass
class ImageBlock:
    type: Literal["image"] = "image"
    source: Dict[str, Any] = field(default_factory=dict)


ContentBlock = Union[
    TextBlock,
    ToolUseBlock,
    ToolResultBlock,
    ThinkingBlock,
    RedactedThinkingBlock,
    ImageBlock,
]


# ---------------------------------------------------------------------------
# Message types
# ---------------------------------------------------------------------------

@dataclass
class UserMessage:
    role: Literal["user"] = "user"
    type: Literal["user"] = "user"
    content: Union[str, List[Any]] = field(default_factory=list)
    uuid: str = field(default_factory=lambda: str(_uuid_mod.uuid4()))
    id: str = field(default_factory=lambda: str(_uuid_mod.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_meta: Optional[bool] = None
    is_visible_in_transcript_only: Optional[bool] = None
    is_virtual: Optional[bool] = None
    is_compact_summary: Optional[bool] = None
    tool_use_result: Optional[Any] = None
    mcp_meta: Optional[Dict[str, Any]] = None
    image_paste_ids: Optional[List[int]] = None
    source_tool_assistant_uuid: Optional[str] = None
    permission_mode: Optional[str] = None
    origin: Optional[Any] = None
    summarize_metadata: Optional[Dict[str, Any]] = None
    # alias used in some lookups
    source_tool_use_id: Optional[str] = None


@dataclass
class AssistantMessage:
    role: Literal["assistant"] = "assistant"
    type: Literal["assistant"] = "assistant"
    content: List[Any] = field(default_factory=list)
    uuid: str = field(default_factory=lambda: str(_uuid_mod.uuid4()))
    id: str = field(default_factory=lambda: str(_uuid_mod.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    stop_reason: Optional[str] = None
    model: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    is_api_error_message: bool = False
    api_error: Optional[Any] = None
    error: Optional[Any] = None
    error_details: Optional[str] = None
    is_virtual: Optional[bool] = None
    request_id: Optional[str] = None
    is_meta: Optional[bool] = None
    advisor_model: Optional[str] = None
    # Nested "message" dict as returned by API (mirrors TS shape)
    message: Optional[Dict[str, Any]] = None

    def __post_init__(self) -> None:
        # Build the message dict lazily from flat fields when not provided
        if self.message is None:
            self.message = {
                "id": self.id,
                "role": "assistant",
                "type": "message",
                "model": self.model or SYNTHETIC_MODEL,
                "stop_reason": self.stop_reason or "stop_sequence",
                "stop_sequence": "",
                "content": self.content,
                "usage": self.usage or {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
                "container": None,
                "context_management": None,
            }


@dataclass
class SystemMessage:
    """Generic system message — holds specialised subtype info as extra fields."""
    role: Literal["system"] = "system"
    type: Literal["system"] = "system"
    subtype: str = "informational"
    content: str = ""
    uuid: str = field(default_factory=lambda: str(_uuid_mod.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    is_meta: bool = False
    level: str = "info"
    tool_use_id: Optional[str] = None
    prevent_continuation: Optional[bool] = None
    # Subtype-specific extra fields stored in extra_data
    extra_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProgressMessage:
    type: Literal["progress"] = "progress"
    tool_use_id: str = ""
    parent_tool_use_id: str = ""
    data: Any = None
    uuid: str = field(default_factory=lambda: str(_uuid_mod.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class AttachmentMessage:
    type: Literal["attachment"] = "attachment"
    attachment: Any = None
    uuid: str = field(default_factory=lambda: str(_uuid_mod.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# Normalized variants (single content-block per message)
NormalizedUserMessage = UserMessage
NormalizedAssistantMessage = AssistantMessage

Message = Union[UserMessage, AssistantMessage, SystemMessage, ProgressMessage, AttachmentMessage]
NormalizedMessage = Union[NormalizedUserMessage, NormalizedAssistantMessage, SystemMessage, ProgressMessage, AttachmentMessage]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYNTHETIC_MODEL = "<synthetic>"

INTERRUPT_MESSAGE = "[Request interrupted by user]"
INTERRUPT_MESSAGE_FOR_TOOL_USE = "[Request interrupted by user for tool use]"
CANCEL_MESSAGE = (
    "The user doesn't want to take this action right now. STOP what you are doing "
    "and wait for the user to tell you how to proceed."
)
REJECT_MESSAGE = (
    "The user doesn't want to proceed with this tool use. The tool use was rejected "
    "(eg. if it was a file edit, the new_string was NOT written to the file). STOP what "
    "you are doing and wait for the user to tell you how to proceed."
)
REJECT_MESSAGE_WITH_REASON_PREFIX = (
    "The user doesn't want to proceed with this tool use. The tool use was rejected "
    "(eg. if it was a file edit, the new_string was NOT written to the file). To tell "
    "you how to proceed, the user said:\n"
)
SUBAGENT_REJECT_MESSAGE = (
    "Permission for this tool use was denied. The tool use was rejected (eg. if it was "
    "a file edit, the new_string was NOT written to the file). Try a different approach "
    "or report the limitation to complete your task."
)
SUBAGENT_REJECT_MESSAGE_WITH_REASON_PREFIX = (
    "Permission for this tool use was denied. The tool use was rejected (eg. if it was "
    "a file edit, the new_string was NOT written to the file). The user said:\n"
)
PLAN_REJECTION_PREFIX = (
    "The agent proposed a plan that was rejected by the user. The user chose to stay in "
    "plan mode rather than proceed with implementation.\n\nRejected plan:\n"
)
NO_RESPONSE_REQUESTED = "No response requested."

# Synthetic tool result placeholder — exported so HFI submission can reject payloads with it
SYNTHETIC_TOOL_RESULT_PLACEHOLDER = "[Tool result missing due to internal error]"

DENIAL_WORKAROUND_GUIDANCE = (
    "IMPORTANT: You *may* attempt to accomplish this action using other tools that might "
    "naturally be used to accomplish this goal, e.g. using head instead of cat. But you "
    "*should not* attempt to work around this denial in malicious ways, e.g. do not use "
    "your ability to run tests to execute non-test actions. You should only try to work "
    "around this restriction in reasonable ways that do not attempt to bypass the intent "
    "behind this denial. If you believe this capability is essential to complete the "
    "user's request, STOP and explain to the user what you were trying to do and why you "
    "need this permission. Let the user decide how to proceed."
)

SYNTHETIC_MESSAGES: Set[str] = {
    INTERRUPT_MESSAGE,
    INTERRUPT_MESSAGE_FOR_TOOL_USE,
    CANCEL_MESSAGE,
    REJECT_MESSAGE,
    NO_RESPONSE_REQUESTED,
}

# Prefix used by UI to detect classifier denials
_AUTO_MODE_REJECTION_PREFIX = "Permission for this action has been denied. Reason: "

_MEMORY_CORRECTION_HINT = (
    "\n\nNote: The user's next message may contain a correction or preference. "
    "Pay close attention — if they explain what went wrong or how they'd prefer "
    "you to work, consider saving that to memory for future sessions."
)

_TOOL_REFERENCE_TURN_BOUNDARY = "Tool loaded."

# Empty lookups type alias
MessageLookups = Dict[str, Any]

EMPTY_LOOKUPS: MessageLookups = {
    "siblingToolUseIDs": {},
    "progressMessagesByToolUseID": {},
    "inProgressHookCounts": {},
    "resolvedHookCounts": {},
    "toolResultByToolUseID": {},
    "toolUseByToolUseID": {},
    "normalizedMessageCount": 0,
    "resolvedToolUseIDs": set(),
    "erroredToolUseIDs": set(),
}

EMPTY_STRING_SET: Set[str] = frozenset()


# ---------------------------------------------------------------------------
# Helper: current ISO timestamp
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Simple feature flag stub (returns False for all flags in this port)
# ---------------------------------------------------------------------------

def _feature(flag: str) -> bool:  # noqa: ARG001
    return False


# ---------------------------------------------------------------------------
# Memory correction hint
# ---------------------------------------------------------------------------

def with_memory_correction_hint(message: str) -> str:
    """
    Append a memory correction hint to a rejection/cancellation message
    when auto-memory is enabled and the GrowthBook flag is on.
    """
    # In the Python port, auto-memory and GrowthBook are not wired up;
    # return the message unchanged.
    return message


# ---------------------------------------------------------------------------
# Short message ID derivation
# ---------------------------------------------------------------------------

def _int_to_base36(n: int) -> str:
    """Convert a non-negative integer to a base-36 string."""
    if n == 0:
        return "0"
    digits = []
    while n:
        digits.append("0123456789abcdefghijklmnopqrstuvwxyz"[n % 36])
        n //= 36
    return "".join(reversed(digits))


def derive_short_message_id(uuid_str: str) -> str:
    """
    Derive a short stable 6-char base36 string from a UUID.
    Deterministic: same UUID always produces the same short ID.
    """
    hex_str = uuid_str.replace("-", "")[:10]
    try:
        return _int_to_base36(int(hex_str, 16))[:6]
    except ValueError:
        return "000000"


# ---------------------------------------------------------------------------
# Permission denial helpers
# ---------------------------------------------------------------------------

def AUTO_REJECT_MESSAGE(tool_name: str) -> str:
    return f"Permission to use {tool_name} has been denied. {DENIAL_WORKAROUND_GUIDANCE}"


def DONT_ASK_REJECT_MESSAGE(tool_name: str) -> str:
    return (
        f"Permission to use {tool_name} has been denied because Claude Code is running "
        f"in don't ask mode. {DENIAL_WORKAROUND_GUIDANCE}"
    )


def is_classifier_denial(content: str) -> bool:
    """Check if a tool result message is a classifier denial."""
    return content.startswith(_AUTO_MODE_REJECTION_PREFIX)


def build_yolo_rejection_message(reason: str) -> str:
    """
    Build a rejection message for auto mode classifier denials.
    """
    prefix = _AUTO_MODE_REJECTION_PREFIX
    rule_hint = (
        "To allow this type of action in the future, the user can add a Bash permission "
        "rule to their settings."
    )
    return (
        f"{prefix}{reason}. "
        f"If you have other tasks that don't depend on this action, continue working on those. "
        f"{DENIAL_WORKAROUND_GUIDANCE} "
        f"{rule_hint}"
    )


def build_classifier_unavailable_message(tool_name: str, classifier_model: str) -> str:
    """
    Build a message for when the auto mode classifier is temporarily unavailable.
    """
    return (
        f"{classifier_model} is temporarily unavailable, so auto mode cannot determine "
        f"the safety of {tool_name} right now. Wait briefly and then try this action again. "
        "If it keeps failing, continue with other tasks that don't require this action and "
        "come back to it later. Note: reading files, searching code, and other read-only "
        "operations do not require the classifier and can still be used."
    )


# ---------------------------------------------------------------------------
# Message predicate helpers
# ---------------------------------------------------------------------------

def _get_message_content_first_block(message: Message) -> Optional[Dict[str, Any]]:
    """Extract the first content block from a message, or None."""
    if isinstance(message, (ProgressMessage, AttachmentMessage, SystemMessage)):
        return None
    content = message.content
    if isinstance(content, list) and content:
        block = content[0]
        if isinstance(block, dict):
            return block
        if hasattr(block, "type"):
            return vars(block)
    return None


def is_synthetic_message(message: Message) -> bool:
    """Return True if the message is a known synthetic message."""
    if isinstance(message, (ProgressMessage, AttachmentMessage, SystemMessage)):
        return False
    content = message.content
    if isinstance(content, list) and content:
        first = content[0]
        text = None
        if isinstance(first, dict):
            if first.get("type") == "text":
                text = first.get("text")
        elif isinstance(first, TextBlock):
            text = first.text
        if text is not None:
            return text in SYNTHETIC_MESSAGES
    return False


def _is_synthetic_api_error_message(message: Message) -> bool:
    return (
        isinstance(message, AssistantMessage)
        and message.is_api_error_message is True
        and (
            (message.message or {}).get("model") == SYNTHETIC_MODEL
            or message.model == SYNTHETIC_MODEL
        )
    )


def get_last_assistant_message(
    messages: List[Message],
) -> Optional[AssistantMessage]:
    """Return the last AssistantMessage in the list, or None."""
    for msg in reversed(messages):
        if isinstance(msg, AssistantMessage):
            return msg
    return None


def has_tool_calls_in_last_assistant_turn(messages: List[Message]) -> bool:
    """Return True if the most recent assistant message contains tool_use blocks."""
    for msg in reversed(messages):
        if isinstance(msg, AssistantMessage):
            content = msg.content
            if isinstance(content, list):
                return any(
                    (isinstance(b, dict) and b.get("type") == "tool_use")
                    or (hasattr(b, "type") and b.type == "tool_use")
                    for b in content
                )
    return False


# ---------------------------------------------------------------------------
# Message creation
# ---------------------------------------------------------------------------

def _default_usage() -> Dict[str, Any]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        "server_tool_use": {"web_search_requests": 0, "web_fetch_requests": 0},
        "service_tier": None,
        "cache_creation": {
            "ephemeral_1h_input_tokens": 0,
            "ephemeral_5m_input_tokens": 0,
        },
        "inference_geo": None,
        "iterations": None,
        "speed": None,
    }


def _base_create_assistant_message(
    *,
    content: List[Any],
    is_api_error_message: bool = False,
    api_error: Optional[Any] = None,
    error: Optional[Any] = None,
    error_details: Optional[str] = None,
    is_virtual: Optional[bool] = None,
    usage: Optional[Dict[str, Any]] = None,
) -> AssistantMessage:
    if usage is None:
        usage = _default_usage()
    msg_id = str(_uuid_mod.uuid4())
    msg_uuid = str(_uuid_mod.uuid4())
    ts = _now_iso()
    inner_message = {
        "id": msg_id,
        "container": None,
        "model": SYNTHETIC_MODEL,
        "role": "assistant",
        "stop_reason": "stop_sequence",
        "stop_sequence": "",
        "type": "message",
        "usage": usage,
        "content": content,
        "context_management": None,
    }
    result = AssistantMessage(
        type="assistant",
        role="assistant",
        uuid=msg_uuid,
        timestamp=ts,
        content=content,
        message=inner_message,
        is_api_error_message=is_api_error_message,
        api_error=api_error,
        error=error,
        error_details=error_details,
        is_virtual=is_virtual,
        usage=usage,
        model=SYNTHETIC_MODEL,
    )
    return result


def create_assistant_message(
    *,
    content: Union[str, List[Any]],
    usage: Optional[Dict[str, Any]] = None,
    is_virtual: Optional[bool] = None,
) -> AssistantMessage:
    """Create an AssistantMessage from a string or list of content blocks."""
    if isinstance(content, str):
        blocks: List[Any] = [
            {"type": "text", "text": content if content else NO_CONTENT_MESSAGE}
        ]
    else:
        blocks = content
    return _base_create_assistant_message(content=blocks, usage=usage, is_virtual=is_virtual)


def create_assistant_api_error_message(
    *,
    content: str,
    api_error: Optional[Any] = None,
    error: Optional[Any] = None,
    error_details: Optional[str] = None,
) -> AssistantMessage:
    """Create an error AssistantMessage."""
    blocks: List[Any] = [
        {"type": "text", "text": content if content else NO_CONTENT_MESSAGE}
    ]
    return _base_create_assistant_message(
        content=blocks,
        is_api_error_message=True,
        api_error=api_error,
        error=error,
        error_details=error_details,
    )


def create_user_message(
    *,
    content: Union[str, List[Any]],
    is_meta: Optional[bool] = None,
    is_visible_in_transcript_only: Optional[bool] = None,
    is_virtual: Optional[bool] = None,
    is_compact_summary: Optional[bool] = None,
    tool_use_result: Optional[Any] = None,
    mcp_meta: Optional[Dict[str, Any]] = None,
    uuid: Optional[str] = None,
    timestamp: Optional[str] = None,
    image_paste_ids: Optional[List[int]] = None,
    source_tool_assistant_uuid: Optional[str] = None,
    permission_mode: Optional[str] = None,
    origin: Optional[Any] = None,
    summarize_metadata: Optional[Dict[str, Any]] = None,
) -> UserMessage:
    """Create a UserMessage."""
    effective_content: Union[str, List[Any]] = content if content else NO_CONTENT_MESSAGE
    return UserMessage(
        type="user",
        role="user",
        content=effective_content,
        uuid=uuid or str(_uuid_mod.uuid4()),
        id=str(_uuid_mod.uuid4()),
        timestamp=timestamp or _now_iso(),
        is_meta=is_meta,
        is_visible_in_transcript_only=is_visible_in_transcript_only,
        is_virtual=is_virtual,
        is_compact_summary=is_compact_summary,
        tool_use_result=tool_use_result,
        mcp_meta=mcp_meta,
        image_paste_ids=image_paste_ids,
        source_tool_assistant_uuid=source_tool_assistant_uuid,
        permission_mode=permission_mode,
        origin=origin,
        summarize_metadata=summarize_metadata,
    )


def prepare_user_content(
    *,
    input_string: str,
    preceding_input_blocks: List[Any],
) -> Union[str, List[Any]]:
    """Combine preceding content blocks with a string input."""
    if not preceding_input_blocks:
        return input_string
    return [*preceding_input_blocks, {"text": input_string, "type": "text"}]


def create_user_interruption_message(*, tool_use: bool = False) -> UserMessage:
    """Create a synthetic interruption UserMessage."""
    text = INTERRUPT_MESSAGE_FOR_TOOL_USE if tool_use else INTERRUPT_MESSAGE
    return create_user_message(
        content=[{"type": "text", "text": text}],
    )


def create_synthetic_user_caveat_message() -> UserMessage:
    """
    Creates a new synthetic user caveat message for local commands.
    New message each time so UUIDs are unique.
    """
    return create_user_message(
        content=(
            "<local-command-caveat>Caveat: The messages below were generated by the user "
            "while running local commands. DO NOT respond to these messages or otherwise "
            "consider them in your response unless the user explicitly asks you to."
            "</local-command-caveat>"
        ),
        is_meta=True,
    )


def format_command_input_tags(command_name: str, args: str) -> str:
    """Format command-input breadcrumb tags."""
    return (
        f"<command-name>/{command_name}</command-name>\n"
        f"            <command-message>{command_name}</command-message>\n"
        f"            <command-args>{args}</command-args>"
    )


def create_model_switch_breadcrumbs(
    model_arg: str, resolved_display: str
) -> List[UserMessage]:
    """Build breadcrumb messages for a mid-conversation model switch."""
    return [
        create_synthetic_user_caveat_message(),
        create_user_message(content=format_command_input_tags("model", model_arg)),
        create_user_message(
            content=f"<local-command-stdout>Set model to {resolved_display}</local-command-stdout>"
        ),
    ]


def create_progress_message(
    *,
    tool_use_id: str,
    parent_tool_use_id: str,
    data: Any,
) -> ProgressMessage:
    """Create a ProgressMessage."""
    return ProgressMessage(
        type="progress",
        tool_use_id=tool_use_id,
        parent_tool_use_id=parent_tool_use_id,
        data=data,
        uuid=str(_uuid_mod.uuid4()),
        timestamp=_now_iso(),
    )


def create_tool_result_stop_message(tool_use_id: str) -> Dict[str, Any]:
    """Create a ToolResultBlockParam for a cancelled tool use."""
    return {
        "type": "tool_result",
        "content": CANCEL_MESSAGE,
        "is_error": True,
        "tool_use_id": tool_use_id,
    }


# ---------------------------------------------------------------------------
# extract_tag — extract content from an XML-like tag, handling nesting
# ---------------------------------------------------------------------------

def extract_tag(html: str, tag_name: str) -> Optional[str]:
    """
    Extract content from the first occurrence of <tag_name>...</tag_name>,
    handling nested same-name tags.
    """
    if not html.strip() or not tag_name.strip():
        return None

    escaped = re.escape(tag_name)
    pattern = re.compile(
        rf"<{escaped}(?:\s+[^>]*)?>[\s\S]*?</{escaped}>",
        re.IGNORECASE,
    )
    opening_re = re.compile(rf"<{escaped}(?:\s+[^>]*?)?>", re.IGNORECASE)
    closing_re = re.compile(rf"</{escaped}>", re.IGNORECASE)
    inner_re = re.compile(
        rf"<{escaped}(?:\s+[^>]*)?>(?P<content>[\s\S]*?)</{escaped}>",
        re.IGNORECASE,
    )

    last_index = 0
    for match in inner_re.finditer(html):
        content = match.group("content")
        before_match = html[last_index : match.start()]

        depth = 0
        for _ in opening_re.finditer(before_match):
            depth += 1
        for _ in closing_re.finditer(before_match):
            depth -= 1

        if depth == 0 and content:
            return content
        last_index = match.start() + len(match.group(0))

    return None


# ---------------------------------------------------------------------------
# is_not_empty_message
# ---------------------------------------------------------------------------

def is_not_empty_message(message: Message) -> bool:
    """Return True if the message has non-empty content."""
    if isinstance(message, (ProgressMessage, AttachmentMessage, SystemMessage)):
        return True

    content = message.content

    if isinstance(content, str):
        return content.strip() != ""

    if not isinstance(content, list) or len(content) == 0:
        return False

    # Skip multi-block messages — assume non-empty
    if len(content) > 1:
        return True

    first = content[0]
    block_type = first.get("type") if isinstance(first, dict) else getattr(first, "type", None)
    if block_type != "text":
        return True

    text = first.get("text") if isinstance(first, dict) else getattr(first, "text", "")
    return (
        text.strip() != ""
        and text != NO_CONTENT_MESSAGE
        and text != INTERRUPT_MESSAGE_FOR_TOOL_USE
    )


# ---------------------------------------------------------------------------
# derive_uuid — deterministic UUID derivation from parent + index
# ---------------------------------------------------------------------------

def derive_uuid(parent_uuid: str, index: int) -> str:
    """
    Derive a stable UUID-shaped string from a parent UUID + content block index.
    Used to maintain stable IDs when normalizing multi-block messages.
    """
    hex_suffix = format(index, "012x")
    return parent_uuid[:24] + hex_suffix


# ---------------------------------------------------------------------------
# normalize_messages — split multi-block messages to single-block
# ---------------------------------------------------------------------------

def normalize_messages(
    messages: List[Message],
) -> List[NormalizedMessage]:
    """
    Split messages so each content block gets its own message.
    Mirrors the TS overloaded normalizeMessages function.
    """
    is_new_chain = False
    result: List[NormalizedMessage] = []

    for message in messages:
        if isinstance(message, AssistantMessage):
            content = message.content
            if not isinstance(content, list):
                content = [{"type": "text", "text": str(content)}]
            is_new_chain = is_new_chain or len(content) > 1
            for index, block in enumerate(content):
                msg_uuid = derive_uuid(message.uuid, index) if is_new_chain else message.uuid
                inner = dict(message.message or {})
                inner["content"] = [block]
                inner["context_management"] = inner.get("context_management")
                nm = AssistantMessage(
                    type="assistant",
                    role="assistant",
                    uuid=msg_uuid,
                    timestamp=message.timestamp,
                    content=[block],
                    message=inner,
                    is_meta=message.is_meta,
                    is_virtual=message.is_virtual,
                    request_id=message.request_id,
                    error=message.error,
                    is_api_error_message=message.is_api_error_message,
                    advisor_model=message.advisor_model,
                )
                result.append(nm)

        elif isinstance(message, (AttachmentMessage, ProgressMessage, SystemMessage)):
            result.append(message)

        elif isinstance(message, UserMessage):
            content = message.content
            if isinstance(content, str):
                msg_uuid = derive_uuid(message.uuid, 0) if is_new_chain else message.uuid
                nm = UserMessage(
                    **{
                        **vars(message),
                        "uuid": msg_uuid,
                        "content": [{"type": "text", "text": content}],
                    }
                )
                result.append(nm)
            else:
                is_new_chain = is_new_chain or len(content) > 1
                image_index = 0
                for index, block in enumerate(content):
                    is_image = (
                        (isinstance(block, dict) and block.get("type") == "image")
                        or (hasattr(block, "type") and block.type == "image")
                    )
                    image_id: Optional[int] = None
                    if is_image and message.image_paste_ids:
                        if image_index < len(message.image_paste_ids):
                            image_id = message.image_paste_ids[image_index]
                        image_index += 1
                    msg_uuid = derive_uuid(message.uuid, index) if is_new_chain else message.uuid
                    nm = create_user_message(
                        content=[block],
                        tool_use_result=message.tool_use_result,
                        mcp_meta=message.mcp_meta,
                        is_meta=message.is_meta,
                        is_visible_in_transcript_only=message.is_visible_in_transcript_only,
                        is_virtual=message.is_virtual,
                        timestamp=message.timestamp,
                        image_paste_ids=[image_id] if image_id is not None else None,
                        origin=message.origin,
                    )
                    nm.uuid = msg_uuid
                    result.append(nm)

    return result


# ---------------------------------------------------------------------------
# Tool-use predicates
# ---------------------------------------------------------------------------

def _content_list(message: Message) -> List[Any]:
    """Return the content as a list, or []."""
    if isinstance(message, (ProgressMessage, AttachmentMessage, SystemMessage)):
        return []
    content = message.content
    if isinstance(content, list):
        return content
    return [{"type": "text", "text": str(content)}]


def _first_block(content: List[Any]) -> Optional[Dict[str, Any]]:
    if not content:
        return None
    b = content[0]
    if isinstance(b, dict):
        return b
    if hasattr(b, "__dict__"):
        return vars(b)
    return None


def is_tool_use_request_message(message: Message) -> bool:
    """Return True if this is an assistant message containing tool_use blocks."""
    if not isinstance(message, AssistantMessage):
        return False
    content = _content_list(message)
    return any(
        (isinstance(b, dict) and b.get("type") == "tool_use")
        or (hasattr(b, "type") and b.type == "tool_use")
        for b in content
    )


def is_tool_use_result_message(message: Message) -> bool:
    """Return True if this is a user message containing tool_result blocks."""
    if not isinstance(message, UserMessage):
        return False
    content = message.content
    if isinstance(content, list) and content:
        first = _first_block(content)
        if first and first.get("type") == "tool_result":
            return True
    if message.tool_use_result is not None:
        return True
    return False


# ---------------------------------------------------------------------------
# reorder_messages_in_ui — group tool use/result pairs
# ---------------------------------------------------------------------------

def reorder_messages_in_ui(
    messages: List[Any],
    synthetic_streaming_tool_use_messages: List[AssistantMessage],
) -> List[Any]:
    """
    Re-order messages so tool results appear immediately after their tool use.
    Mirrors TS reorderMessagesInUI.
    """
    from collections import defaultdict

    tool_use_groups: Dict[str, Dict[str, Any]] = {}

    def _get_hook_tool_use_id(msg: Any) -> Optional[str]:
        if isinstance(msg, AttachmentMessage) and isinstance(msg.attachment, dict):
            return msg.attachment.get("toolUseID") or msg.attachment.get("tool_use_id")
        return None

    def _is_hook_attachment(msg: Any) -> bool:
        if not isinstance(msg, AttachmentMessage):
            return False
        att = msg.attachment
        if not isinstance(att, dict):
            return False
        return att.get("type") in {
            "hook_blocking_error",
            "hook_cancelled",
            "hook_error_during_execution",
            "hook_non_blocking_error",
            "hook_success",
            "hook_system_message",
            "hook_additional_context",
            "hook_stopped_continuation",
        }

    # First pass: group
    for msg in messages:
        if is_tool_use_request_message(msg):
            content = _content_list(msg)
            tool_use_id = None
            for b in content:
                bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                if bt == "tool_use":
                    tool_use_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
                    break
            if tool_use_id:
                if tool_use_id not in tool_use_groups:
                    tool_use_groups[tool_use_id] = {
                        "toolUse": None, "preHooks": [], "toolResult": None, "postHooks": []
                    }
                tool_use_groups[tool_use_id]["toolUse"] = msg
            continue

        if _is_hook_attachment(msg):
            hook_event = (msg.attachment or {}).get("hookEvent")
            tool_use_id = _get_hook_tool_use_id(msg)
            if tool_use_id:
                if tool_use_id not in tool_use_groups:
                    tool_use_groups[tool_use_id] = {
                        "toolUse": None, "preHooks": [], "toolResult": None, "postHooks": []
                    }
                if hook_event == "PreToolUse":
                    tool_use_groups[tool_use_id]["preHooks"].append(msg)
                elif hook_event == "PostToolUse":
                    tool_use_groups[tool_use_id]["postHooks"].append(msg)
            continue

        if isinstance(msg, UserMessage):
            content = msg.content if isinstance(msg.content, list) else []
            first = _first_block(content)
            if first and first.get("type") == "tool_result":
                tool_use_id = first.get("tool_use_id")
                if tool_use_id:
                    if tool_use_id not in tool_use_groups:
                        tool_use_groups[tool_use_id] = {
                            "toolUse": None, "preHooks": [], "toolResult": None, "postHooks": []
                        }
                    tool_use_groups[tool_use_id]["toolResult"] = msg
                continue

    # Second pass: reconstruct
    result: List[Any] = []
    processed_tool_uses: Set[str] = set()

    for msg in messages:
        if is_tool_use_request_message(msg):
            content = _content_list(msg)
            tool_use_id = None
            for b in content:
                bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                if bt == "tool_use":
                    tool_use_id = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
                    break
            if tool_use_id and tool_use_id not in processed_tool_uses:
                processed_tool_uses.add(tool_use_id)
                group = tool_use_groups.get(tool_use_id, {})
                if group.get("toolUse"):
                    result.append(group["toolUse"])
                    result.extend(group.get("preHooks", []))
                    if group.get("toolResult"):
                        result.append(group["toolResult"])
                    result.extend(group.get("postHooks", []))
            continue

        if _is_hook_attachment(msg):
            continue

        if isinstance(msg, UserMessage):
            content = msg.content if isinstance(msg.content, list) else []
            first = _first_block(content)
            if first and first.get("type") == "tool_result":
                continue

        # Handle api_error deduplication
        if isinstance(msg, SystemMessage) and msg.subtype == "api_error":
            if result and isinstance(result[-1], SystemMessage) and result[-1].subtype == "api_error":
                result[-1] = msg
            else:
                result.append(msg)
            continue

        result.append(msg)

    for msg in synthetic_streaming_tool_use_messages:
        result.append(msg)

    # Keep only the last api_error system message
    last = result[-1] if result else None
    return [
        m for m in result
        if not (isinstance(m, SystemMessage) and m.subtype == "api_error" and m is not last)
    ]


# ---------------------------------------------------------------------------
# Hook helpers
# ---------------------------------------------------------------------------

def _is_hook_attachment_message(message: Message) -> bool:
    if not isinstance(message, AttachmentMessage):
        return False
    att = message.attachment
    if not isinstance(att, dict):
        return False
    return att.get("type") in {
        "hook_blocking_error", "hook_cancelled", "hook_error_during_execution",
        "hook_non_blocking_error", "hook_success", "hook_system_message",
        "hook_additional_context", "hook_stopped_continuation",
    }


def has_unresolved_hooks(
    messages: List[NormalizedMessage],
    tool_use_id: str,
    hook_event: str,
) -> bool:
    """Return True if there are in-progress hooks without a resolved counterpart."""
    in_progress = sum(
        1 for m in messages
        if isinstance(m, ProgressMessage)
        and isinstance(m.data, dict)
        and m.data.get("type") == "hook_progress"
        and m.data.get("hookEvent") == hook_event
        and m.parent_tool_use_id == tool_use_id
    )
    resolved_names: Set[str] = set()
    for m in messages:
        if _is_hook_attachment_message(m):
            att = m.attachment  # type: ignore[union-attr]
            if (
                att.get("toolUseID") == tool_use_id
                and att.get("hookEvent") == hook_event
                and "hookName" in att
            ):
                resolved_names.add(att["hookName"])
    return in_progress > len(resolved_names)


# ---------------------------------------------------------------------------
# Tool-result ID extraction
# ---------------------------------------------------------------------------

def get_tool_result_ids(
    normalized_messages: List[NormalizedMessage],
) -> Dict[str, bool]:
    """Return a dict mapping tool_use_id → is_error for all tool results."""
    result: Dict[str, bool] = {}
    for m in normalized_messages:
        if isinstance(m, UserMessage) and isinstance(m.content, list):
            first = _first_block(m.content)
            if first and first.get("type") == "tool_result":
                result[first["tool_use_id"]] = bool(first.get("is_error", False))
    return result


def get_sibling_tool_use_ids(
    message: NormalizedMessage,
    messages: List[Message],
) -> Set[str]:
    """Return the set of tool-use IDs that share the same API message ID."""
    tool_use_id = get_tool_use_id(message)
    if not tool_use_id:
        return set()

    unnormalized = None
    for m in messages:
        if isinstance(m, AssistantMessage) and isinstance(m.content, list):
            for b in m.content:
                bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                bid = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
                if bt == "tool_use" and bid == tool_use_id:
                    unnormalized = m
                    break
        if unnormalized:
            break

    if not unnormalized:
        return set()

    message_id = (unnormalized.message or {}).get("id") or unnormalized.id
    siblings: Set[str] = set()
    for m in messages:
        if isinstance(m, AssistantMessage) and isinstance(m.content, list):
            mid = (m.message or {}).get("id") or m.id
            if mid == message_id:
                for b in m.content:
                    bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                    bid = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
                    if bt == "tool_use" and bid:
                        siblings.add(bid)
    return siblings


# ---------------------------------------------------------------------------
# build_message_lookups
# ---------------------------------------------------------------------------

def build_message_lookups(
    normalized_messages: List[NormalizedMessage],
    messages: List[Message],
) -> MessageLookups:
    """
    Build pre-computed O(1) lookups for message relationships.
    """
    tool_use_ids_by_message_id: Dict[str, Set[str]] = {}
    tool_use_id_to_message_id: Dict[str, str] = {}
    tool_use_by_tool_use_id: Dict[str, Any] = {}

    for msg in messages:
        if isinstance(msg, AssistantMessage) and isinstance(msg.content, list):
            mid = (msg.message or {}).get("id") or msg.id
            if mid not in tool_use_ids_by_message_id:
                tool_use_ids_by_message_id[mid] = set()
            for b in msg.content:
                bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                bid = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
                if bt == "tool_use" and bid:
                    tool_use_ids_by_message_id[mid].add(bid)
                    tool_use_id_to_message_id[bid] = mid
                    tool_use_by_tool_use_id[bid] = b

    sibling_tool_use_ids: Dict[str, Set[str]] = {
        tool_use_id: tool_use_ids_by_message_id[message_id]
        for tool_use_id, message_id in tool_use_id_to_message_id.items()
    }

    progress_by_tool_use_id: Dict[str, List[ProgressMessage]] = {}
    in_progress_hook_counts: Dict[str, Dict[str, int]] = {}
    resolved_hook_names: Dict[str, Dict[str, Set[str]]] = {}
    tool_result_by_tool_use_id: Dict[str, NormalizedMessage] = {}
    resolved_tool_use_ids: Set[str] = set()
    errored_tool_use_ids: Set[str] = set()

    for msg in normalized_messages:
        if isinstance(msg, ProgressMessage):
            tid = msg.parent_tool_use_id
            if tid not in progress_by_tool_use_id:
                progress_by_tool_use_id[tid] = []
            progress_by_tool_use_id[tid].append(msg)

            if isinstance(msg.data, dict) and msg.data.get("type") == "hook_progress":
                hook_event = msg.data.get("hookEvent", "")
                if tid not in in_progress_hook_counts:
                    in_progress_hook_counts[tid] = {}
                in_progress_hook_counts[tid][hook_event] = (
                    in_progress_hook_counts[tid].get(hook_event, 0) + 1
                )

        if isinstance(msg, UserMessage) and isinstance(msg.content, list):
            for b in msg.content:
                bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                if bt == "tool_result":
                    tid = b.get("tool_use_id") if isinstance(b, dict) else getattr(b, "tool_use_id", None)
                    if tid:
                        tool_result_by_tool_use_id[tid] = msg
                        resolved_tool_use_ids.add(tid)
                        if b.get("is_error") if isinstance(b, dict) else getattr(b, "is_error", False):
                            errored_tool_use_ids.add(tid)

        if isinstance(msg, AssistantMessage) and isinstance(msg.content, list):
            for b in msg.content:
                if isinstance(b, dict) and "tool_use_id" in b:
                    resolved_tool_use_ids.add(b["tool_use_id"])

        if _is_hook_attachment_message(msg):
            att = msg.attachment  # type: ignore[union-attr]
            tid = att.get("toolUseID", "")
            hook_event = att.get("hookEvent", "")
            hook_name = att.get("hookName")
            if hook_name is not None:
                if tid not in resolved_hook_names:
                    resolved_hook_names[tid] = {}
                if hook_event not in resolved_hook_names[tid]:
                    resolved_hook_names[tid][hook_event] = set()
                resolved_hook_names[tid][hook_event].add(hook_name)

    resolved_hook_counts: Dict[str, Dict[str, int]] = {
        tid: {event: len(names) for event, names in by_event.items()}
        for tid, by_event in resolved_hook_names.items()
    }

    # Mark orphaned server_tool_use / mcp_tool_use as errored
    last_msg = messages[-1] if messages else None
    last_assistant_msg_id = (
        (last_msg.message or {}).get("id") or last_msg.id
        if isinstance(last_msg, AssistantMessage)
        else None
    )
    for msg in normalized_messages:
        if not isinstance(msg, AssistantMessage):
            continue
        mid = (msg.message or {}).get("id") or msg.id
        if mid == last_assistant_msg_id:
            continue
        for b in (msg.content or []):
            bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
            bid = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
            if bt in ("server_tool_use", "mcp_tool_use") and bid and bid not in resolved_tool_use_ids:
                resolved_tool_use_ids.add(bid)
                errored_tool_use_ids.add(bid)

    return {
        "siblingToolUseIDs": sibling_tool_use_ids,
        "progressMessagesByToolUseID": progress_by_tool_use_id,
        "inProgressHookCounts": in_progress_hook_counts,
        "resolvedHookCounts": resolved_hook_counts,
        "toolResultByToolUseID": tool_result_by_tool_use_id,
        "toolUseByToolUseID": tool_use_by_tool_use_id,
        "normalizedMessageCount": len(normalized_messages),
        "resolvedToolUseIDs": resolved_tool_use_ids,
        "erroredToolUseIDs": errored_tool_use_ids,
    }


def build_subagent_lookups(
    messages: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Build lookups from subagent/skill progress messages.
    """
    tool_use_by_tool_use_id: Dict[str, Any] = {}
    resolved_tool_use_ids: Set[str] = set()
    tool_result_by_tool_use_id: Dict[str, Any] = {}

    for item in messages:
        msg = item.get("message")
        if isinstance(msg, AssistantMessage) and isinstance(msg.content, list):
            for b in msg.content:
                bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                bid = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
                if bt == "tool_use" and bid:
                    tool_use_by_tool_use_id[bid] = b
        elif isinstance(msg, UserMessage) and isinstance(msg.content, list):
            for b in msg.content:
                bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
                if bt == "tool_result":
                    tid = b.get("tool_use_id") if isinstance(b, dict) else getattr(b, "tool_use_id", None)
                    if tid:
                        resolved_tool_use_ids.add(tid)
                        tool_result_by_tool_use_id[tid] = msg

    in_progress_tool_use_ids = {
        tid for tid in tool_use_by_tool_use_id if tid not in resolved_tool_use_ids
    }

    lookups = {
        **EMPTY_LOOKUPS,
        "toolUseByToolUseID": tool_use_by_tool_use_id,
        "resolvedToolUseIDs": resolved_tool_use_ids,
        "toolResultByToolUseID": tool_result_by_tool_use_id,
    }
    return {"lookups": lookups, "inProgressToolUseIDs": in_progress_tool_use_ids}


# ---------------------------------------------------------------------------
# Lookup-based accessors (O(1))
# ---------------------------------------------------------------------------

def get_sibling_tool_use_ids_from_lookup(
    message: NormalizedMessage,
    lookups: MessageLookups,
) -> Set[str]:
    """Get sibling tool use IDs using pre-computed lookup."""
    tool_use_id = get_tool_use_id(message)
    if not tool_use_id:
        return EMPTY_STRING_SET
    return lookups.get("siblingToolUseIDs", {}).get(tool_use_id, EMPTY_STRING_SET)


def get_progress_messages_from_lookup(
    message: NormalizedMessage,
    lookups: MessageLookups,
) -> List[ProgressMessage]:
    """Get progress messages for a message using pre-computed lookup."""
    tool_use_id = get_tool_use_id(message)
    if not tool_use_id:
        return []
    return lookups.get("progressMessagesByToolUseID", {}).get(tool_use_id, [])


def has_unresolved_hooks_from_lookup(
    tool_use_id: str,
    hook_event: str,
    lookups: MessageLookups,
) -> bool:
    """Check for unresolved hooks using pre-computed lookup."""
    in_progress = (
        lookups.get("inProgressHookCounts", {})
        .get(tool_use_id, {})
        .get(hook_event, 0)
    )
    resolved = (
        lookups.get("resolvedHookCounts", {})
        .get(tool_use_id, {})
        .get(hook_event, 0)
    )
    return in_progress > resolved


def get_tool_use_ids(normalized_messages: List[NormalizedMessage]) -> Set[str]:
    """Return the set of all tool_use IDs in normalized assistant messages."""
    ids: Set[str] = set()
    for m in normalized_messages:
        if not isinstance(m, AssistantMessage):
            continue
        content = m.content if isinstance(m.content, list) else []
        first = _first_block(content)
        if first and first.get("type") == "tool_use":
            bid = first.get("id")
            if bid:
                ids.add(bid)
    return ids


# ---------------------------------------------------------------------------
# reorder_attachments_for_api
# ---------------------------------------------------------------------------

def reorder_attachments_for_api(messages: List[Message]) -> List[Message]:
    """
    Bubble attachments up until they hit a tool result or assistant message.
    O(N) implementation.
    """
    result: List[Message] = []
    pending: List[AttachmentMessage] = []

    for i in range(len(messages) - 1, -1, -1):
        msg = messages[i]
        if isinstance(msg, AttachmentMessage):
            pending.append(msg)
        else:
            is_stopping = isinstance(msg, AssistantMessage) or (
                isinstance(msg, UserMessage)
                and isinstance(msg.content, list)
                and bool(_first_block(msg.content) and _first_block(msg.content).get("type") == "tool_result")  # type: ignore[union-attr]
            )
            if is_stopping and pending:
                for att in pending:
                    result.append(att)
                result.append(msg)
                pending.clear()
            else:
                result.append(msg)

    for att in pending:
        result.append(att)

    result.reverse()
    return result


# ---------------------------------------------------------------------------
# isSystemLocalCommandMessage
# ---------------------------------------------------------------------------

def is_system_local_command_message(message: Message) -> bool:
    """Return True if this is a system/local_command message."""
    return isinstance(message, SystemMessage) and message.subtype == "local_command"


# ---------------------------------------------------------------------------
# strip_tool_reference_blocks_from_user_message
# ---------------------------------------------------------------------------

def _is_tool_reference_block(block: Any) -> bool:
    if isinstance(block, dict):
        return block.get("type") == "tool_reference"
    return getattr(block, "type", None) == "tool_reference"


def strip_tool_reference_blocks_from_user_message(message: UserMessage) -> UserMessage:
    """Strip tool_reference blocks from tool_result content."""
    content = message.content
    if not isinstance(content, list):
        return message

    has_tool_ref = any(
        (isinstance(b, dict) and b.get("type") == "tool_result" and isinstance(b.get("content"), list)
         and any(_is_tool_reference_block(c) for c in b["content"]))
        for b in content
    )
    if not has_tool_ref:
        return message

    new_content = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_result" and isinstance(b.get("content"), list):
            filtered = [c for c in b["content"] if not _is_tool_reference_block(c)]
            if not filtered:
                filtered = [{"type": "text", "text": "[Tool references removed - tool search not enabled]"}]
            new_content.append({**b, "content": filtered})
        else:
            new_content.append(b)

    from dataclasses import replace
    return UserMessage(**{**vars(message), "content": new_content})


def strip_caller_field_from_assistant_message(message: AssistantMessage) -> AssistantMessage:
    """Strip the 'caller' field from tool_use blocks in an assistant message."""
    content = message.content if isinstance(message.content, list) else []
    has_caller = any(
        isinstance(b, dict) and b.get("type") == "tool_use" and b.get("caller") is not None
        for b in content
    )
    if not has_caller:
        return message

    new_content = []
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use":
            new_content.append({
                "type": "tool_use",
                "id": b["id"],
                "name": b["name"],
                "input": b["input"],
            })
        else:
            new_content.append(b)

    new_msg = dict(message.message or {})
    new_msg["content"] = new_content
    return AssistantMessage(**{**vars(message), "content": new_content, "message": new_msg})


# ---------------------------------------------------------------------------
# merge helpers
# ---------------------------------------------------------------------------

def _normalize_user_text_content(content: Union[str, List[Any]]) -> List[Any]:
    if isinstance(content, str):
        return [{"type": "text", "text": content}]
    return list(content)


def _hoist_tool_results(content: List[Any]) -> List[Any]:
    """Move tool_result blocks to the front of a content list."""
    tool_results = [b for b in content if (
        (isinstance(b, dict) and b.get("type") == "tool_result")
        or (hasattr(b, "type") and b.type == "tool_result")
    )]
    others = [b for b in content if b not in tool_results]
    return tool_results + others


def _join_text_at_seam(a: List[Any], b: List[Any]) -> List[Any]:
    """Concatenate two content lists, adding \\n at the text seam."""
    if not a:
        return b
    last_a = a[-1]
    first_b = b[0] if b else None
    if (
        first_b is not None
        and (isinstance(last_a, dict) and last_a.get("type") == "text")
        and (isinstance(first_b, dict) and first_b.get("type") == "text")
    ):
        return [*a[:-1], {**last_a, "text": last_a["text"] + "\n"}, *b]
    return [*a, *b]


def merge_user_messages(a: UserMessage, b: UserMessage) -> UserMessage:
    """Merge two consecutive user messages."""
    last_content = _normalize_user_text_content(a.content)
    current_content = _normalize_user_text_content(b.content)
    merged_uuid = b.uuid if a.is_meta else a.uuid
    merged_content = _hoist_tool_results(_join_text_at_seam(last_content, current_content))
    return UserMessage(**{
        **vars(a),
        "uuid": merged_uuid,
        "content": merged_content,
    })


def merge_user_messages_and_tool_results(a: UserMessage, b: UserMessage) -> UserMessage:
    """Merge user messages, combining tool results."""
    last_content = _normalize_user_text_content(a.content)
    current_content = _normalize_user_text_content(b.content)
    merged = _hoist_tool_results(_merge_user_content_blocks(last_content, current_content))
    return UserMessage(**{**vars(a), "content": merged})


def _smoosh_into_tool_result(
    tr: Dict[str, Any],
    blocks: List[Any],
) -> Optional[Dict[str, Any]]:
    """Fold content blocks into a tool_result's content. Returns None if impossible."""
    if not blocks:
        return tr

    existing = tr.get("content")
    if isinstance(existing, list) and any(_is_tool_reference_block(c) for c in existing):
        return None  # tool_reference constraint

    if tr.get("is_error"):
        blocks = [b for b in blocks if (
            (isinstance(b, dict) and b.get("type") == "text")
            or (hasattr(b, "type") and b.type == "text")
        )]
        if not blocks:
            return tr

    all_text = all(
        (isinstance(b, dict) and b.get("type") == "text")
        or (hasattr(b, "type") and b.type == "text")
        for b in blocks
    )

    if all_text and (existing is None or isinstance(existing, str)):
        texts = [
            (existing or "").strip(),
            *[
                (b.get("text") if isinstance(b, dict) else getattr(b, "text", "")).strip()
                for b in blocks
            ],
        ]
        joined = "\n\n".join(t for t in texts if t)
        return {**tr, "content": joined}

    base: List[Any]
    if existing is None:
        base = []
    elif isinstance(existing, str):
        base = [{"type": "text", "text": existing.strip()}] if existing.strip() else []
    else:
        base = list(existing)

    merged: List[Any] = []
    for b in base + blocks:
        bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
        btext = b.get("text") if isinstance(b, dict) else getattr(b, "text", "")
        if bt == "text":
            t = btext.strip() if btext else ""
            if not t:
                continue
            if merged and (isinstance(merged[-1], dict) and merged[-1].get("type") == "text"):
                prev = merged[-1]
                merged[-1] = {**prev, "text": f"{prev['text']}\n\n{t}"}
            else:
                merged.append({"type": "text", "text": t})
        else:
            merged.append(b)

    return {**tr, "content": merged}


def _merge_user_content_blocks(a: List[Any], b: List[Any]) -> List[Any]:
    """Merge two content block lists, smooshing trailing tool results."""
    last_block = a[-1] if a else None
    if last_block is None:
        return [*a, *b]

    lb_type = last_block.get("type") if isinstance(last_block, dict) else getattr(last_block, "type", None)
    if lb_type != "tool_result":
        return [*a, *b]

    # Legacy smoosh: only when content is a string and all incoming are text
    if (
        isinstance(last_block.get("content") if isinstance(last_block, dict) else None, str)
        and all(
            (isinstance(x, dict) and x.get("type") == "text")
            or (hasattr(x, "type") and x.type == "text")
            for x in b
        )
    ):
        copy = list(a)
        smooshed = _smoosh_into_tool_result(last_block, b)
        if smooshed is not None:
            copy[-1] = smooshed
            return copy

    return [*a, *b]


merge_user_content_blocks = _merge_user_content_blocks


def merge_assistant_messages(a: AssistantMessage, b: AssistantMessage) -> AssistantMessage:
    """Merge two AssistantMessages by concatenating their content."""
    merged_content = list(a.content or []) + list(b.content or [])
    new_msg = dict(a.message or {})
    new_msg["content"] = merged_content
    return AssistantMessage(**{**vars(a), "content": merged_content, "message": new_msg})


# ---------------------------------------------------------------------------
# normalize_messages_for_api
# ---------------------------------------------------------------------------

def normalize_messages_for_api(
    messages: List[Message],
    tools: Optional[List[Any]] = None,
) -> List[Union[UserMessage, AssistantMessage]]:
    """
    Convert internal messages to API-ready format.
    Original TS: normalizeMessagesForAPI
    """
    if tools is None:
        tools = []

    reordered = reorder_attachments_for_api(messages)
    reordered = [
        m for m in reordered
        if not (isinstance(m, (UserMessage, AssistantMessage)) and m.is_virtual)
    ]

    result: List[Union[UserMessage, AssistantMessage]] = []

    def _last() -> Optional[Union[UserMessage, AssistantMessage]]:
        return result[-1] if result else None

    for message in reordered:
        if isinstance(message, ProgressMessage):
            continue
        if isinstance(message, SystemMessage) and not is_system_local_command_message(message):
            continue
        if _is_synthetic_api_error_message(message):
            continue

        if is_system_local_command_message(message):
            sys_msg = message  # type: ignore[assignment]
            user_msg = create_user_message(
                content=sys_msg.content,  # type: ignore[attr-defined]
                uuid=sys_msg.uuid,
                timestamp=sys_msg.timestamp,
            )
            last = _last()
            if last and isinstance(last, UserMessage):
                result[-1] = merge_user_messages(last, user_msg)
            else:
                result.append(user_msg)
            continue

        if isinstance(message, UserMessage):
            normalized = strip_tool_reference_blocks_from_user_message(message)
            last = _last()
            if last and isinstance(last, UserMessage):
                result[-1] = merge_user_messages(last, normalized)
            else:
                result.append(normalized)
            continue

        if isinstance(message, AssistantMessage):
            # Normalize tool inputs for API
            content = message.content if isinstance(message.content, list) else []
            new_content = []
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    new_content.append({
                        "type": "tool_use",
                        "id": block["id"],
                        "name": block["name"],
                        "input": block.get("input", {}),
                    })
                else:
                    new_content.append(block)
            new_msg = dict(message.message or {})
            new_msg["content"] = new_content
            normalized_asst = AssistantMessage(**{
                **vars(message),
                "content": new_content,
                "message": new_msg,
            })

            # Try to merge with a previous assistant message that has same ID
            for i in range(len(result) - 1, -1, -1):
                m = result[i]
                if isinstance(m, UserMessage):
                    content_i = m.content if isinstance(m.content, list) else []
                    if content_i and _first_block(content_i) and _first_block(content_i).get("type") == "tool_result":  # type: ignore[union-attr]
                        continue
                    break
                if isinstance(m, AssistantMessage):
                    mid = (m.message or {}).get("id") or m.id
                    norm_mid = (normalized_asst.message or {}).get("id") or normalized_asst.id
                    if mid == norm_mid:
                        result[i] = merge_assistant_messages(m, normalized_asst)
                        break
                    continue
            else:
                result.append(normalized_asst)
            # Always try to append if not merged
            if not any(
                isinstance(r, AssistantMessage)
                and ((r.message or {}).get("id") or r.id) == ((normalized_asst.message or {}).get("id") or normalized_asst.id)
                for r in result
            ):
                result.append(normalized_asst)
            continue

        if isinstance(message, AttachmentMessage):
            att_messages = normalize_attachment_for_api(message.attachment)
            last = _last()
            if last and isinstance(last, UserMessage):
                for att_msg in att_messages:
                    result[-1] = merge_user_messages_and_tool_results(result[-1], att_msg)  # type: ignore[arg-type]
            else:
                result.extend(att_messages)
            continue

    return _filter_orphaned_thinking_only_messages_flat(result)


# ---------------------------------------------------------------------------
# normalize_content_from_api — clean up API response content
# ---------------------------------------------------------------------------

def normalize_content_from_api(
    content_blocks: Optional[List[Any]],
    tools: Optional[List[Any]] = None,
    agent_id: Optional[str] = None,
) -> List[Any]:
    """
    Normalise content blocks from an API response.
    Original TS: normalizeContentFromAPI
    """
    if not content_blocks:
        return []
    if tools is None:
        tools = []

    result = []
    for block in content_blocks:
        if not isinstance(block, dict):
            result.append(block)
            continue

        bt = block.get("type")
        if bt == "tool_use":
            raw_input = block.get("input", {})
            if isinstance(raw_input, str):
                try:
                    import json
                    normalized_input = json.loads(raw_input) if raw_input else {}
                except (json.JSONDecodeError, ValueError):
                    normalized_input = {}
            else:
                normalized_input = raw_input
            result.append({**block, "input": normalized_input})
        elif bt == "server_tool_use":
            raw_input = block.get("input", {})
            if isinstance(raw_input, str):
                try:
                    import json
                    normalized_input = json.loads(raw_input) if raw_input else {}
                except (json.JSONDecodeError, ValueError):
                    normalized_input = {}
            else:
                normalized_input = raw_input
            result.append({**block, "input": normalized_input})
        else:
            result.append(block)

    return result


# ---------------------------------------------------------------------------
# Text extraction / predicates
# ---------------------------------------------------------------------------

_STRIPPED_TAGS_RE = re.compile(
    r"<(commit_analysis|context|function_analysis|pr_analysis)>.*?</\1>\n?",
    re.DOTALL,
)


def strip_prompt_xml_tags(content: str) -> str:
    """Strip commit_analysis, context, function_analysis, pr_analysis tags."""
    return _STRIPPED_TAGS_RE.sub("", content).strip()


def is_empty_message_text(text: str) -> bool:
    """Return True if the text is effectively empty after stripping XML tags."""
    return strip_prompt_xml_tags(text).strip() == "" or text.strip() == NO_CONTENT_MESSAGE


def get_tool_use_id(message: NormalizedMessage) -> Optional[str]:
    """Return the tool_use ID associated with a message, or None."""
    if isinstance(message, AttachmentMessage):
        if _is_hook_attachment_message(message):
            return (message.attachment or {}).get("toolUseID")
        return None

    if isinstance(message, AssistantMessage):
        content = message.content if isinstance(message.content, list) else []
        first = _first_block(content)
        if first and first.get("type") == "tool_use":
            return first.get("id")
        return None

    if isinstance(message, UserMessage):
        if message.source_tool_use_id:
            return message.source_tool_use_id
        content = message.content if isinstance(message.content, list) else []
        first = _first_block(content)
        if first and first.get("type") == "tool_result":
            return first.get("tool_use_id")
        return None

    if isinstance(message, ProgressMessage):
        return message.tool_use_id

    if isinstance(message, SystemMessage):
        if message.subtype == "informational":
            return message.tool_use_id
        return None

    return None


def filter_unresolved_tool_uses(messages: List[Message]) -> List[Message]:
    """Remove assistant messages whose tool_use blocks have no matching tool_result."""
    tool_use_ids: Set[str] = set()
    tool_result_ids: Set[str] = set()

    for msg in messages:
        if not isinstance(msg, (UserMessage, AssistantMessage)):
            continue
        content = msg.content if isinstance(msg.content, list) else []
        for b in content:
            bt = b.get("type") if isinstance(b, dict) else getattr(b, "type", None)
            bid = b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
            if bt == "tool_use" and bid:
                tool_use_ids.add(bid)
            if bt == "tool_result":
                tid = b.get("tool_use_id") if isinstance(b, dict) else getattr(b, "tool_use_id", None)
                if tid:
                    tool_result_ids.add(tid)

    unresolved = tool_use_ids - tool_result_ids
    if not unresolved:
        return messages

    result = []
    for msg in messages:
        if not isinstance(msg, AssistantMessage):
            result.append(msg)
            continue
        content = msg.content if isinstance(msg.content, list) else []
        tool_use_block_ids = [
            b.get("id") if isinstance(b, dict) else getattr(b, "id", None)
            for b in content
            if (isinstance(b, dict) and b.get("type") == "tool_use")
            or (hasattr(b, "type") and b.type == "tool_use")
        ]
        if not tool_use_block_ids:
            result.append(msg)
            continue
        if all(bid in unresolved for bid in tool_use_block_ids if bid):
            continue  # remove
        result.append(msg)

    return result


def get_assistant_message_text(message: Message) -> Optional[str]:
    """Extract and join all text blocks from an assistant message."""
    if not isinstance(message, AssistantMessage):
        return None
    content = message.content if isinstance(message.content, list) else []
    texts = [
        b.get("text") if isinstance(b, dict) else getattr(b, "text", "")
        for b in content
        if (isinstance(b, dict) and b.get("type") == "text")
        or (hasattr(b, "type") and b.type == "text")
    ]
    joined = "\n".join(t for t in texts if t).strip()
    return joined or None


def get_user_message_text(message: Union[Message, NormalizedMessage]) -> Optional[str]:
    """Extract text content from a user message."""
    if not isinstance(message, UserMessage):
        return None
    return get_content_text(message.content)


def extract_text_content(
    blocks: List[Any],
    separator: str = "",
) -> str:
    """Extract and join text blocks from a content list."""
    texts = [
        b.get("text") if isinstance(b, dict) else getattr(b, "text", "")
        for b in blocks
        if (isinstance(b, dict) and b.get("type") == "text")
        or (hasattr(b, "type") and b.type == "text")
    ]
    return separator.join(t for t in texts if t is not None)


def get_content_text(
    content: Union[str, List[Any]],
) -> Optional[str]:
    """Return text from string or list content."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return extract_text_content(content, "\n").strip() or None
    return None


def text_for_resubmit(msg: UserMessage) -> Optional[Dict[str, str]]:
    """Extract text and mode for message resubmission."""
    content = get_user_message_text(msg)
    if content is None:
        return None
    bash = extract_tag(content, "bash-input")
    if bash:
        return {"text": bash, "mode": "bash"}
    cmd = extract_tag(content, "command-name")
    if cmd:
        args = extract_tag(content, "command-args") or ""
        return {"text": f"{cmd} {args}", "mode": "prompt"}
    return {"text": content, "mode": "prompt"}


# ---------------------------------------------------------------------------
# Stream type stubs
# ---------------------------------------------------------------------------

class StreamingToolUse:
    def __init__(self, index: int, content_block: Any, unparsed_tool_input: str) -> None:
        self.index = index
        self.content_block = content_block
        self.unparsed_tool_input = unparsed_tool_input


class StreamingThinking:
    def __init__(
        self,
        thinking: str,
        is_streaming: bool,
        streaming_ended_at: Optional[int] = None,
    ) -> None:
        self.thinking = thinking
        self.is_streaming = is_streaming
        self.streaming_ended_at = streaming_ended_at


def handle_message_from_stream(
    message: Any,
    on_message: Callable[[Any], None],
    on_update_length: Callable[[str], None],
    on_set_stream_mode: Callable[[str], None],
    on_streaming_tool_uses: Callable[[Callable[[List[Any]], List[Any]]], None],
    on_tombstone: Optional[Callable[[Any], None]] = None,
    on_streaming_thinking: Optional[Callable[[Callable[[Any], Any]], None]] = None,
    on_api_metrics: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_streaming_text: Optional[Callable[[Callable[[Optional[str]], Optional[str]]], None]] = None,
) -> None:
    """
    Handle messages from a stream, dispatching events to callbacks.
    Minimal Python port — UI streaming details omitted.
    """
    if not isinstance(message, dict):
        # Plain message object
        if getattr(message, "type", None) == "tombstone":
            on_tombstone and on_tombstone(getattr(message, "message", message))
            return
        if getattr(message, "type", None) == "tool_use_summary":
            return
        if getattr(message, "type", None) == "assistant":
            content = getattr(message, "content", [])
            for block in (content if isinstance(content, list) else []):
                bt = block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
                if bt == "thinking":
                    thinking_text = block.get("thinking") if isinstance(block, dict) else getattr(block, "thinking", "")
                    if on_streaming_thinking:
                        on_streaming_thinking(lambda _: StreamingThinking(
                            thinking=thinking_text,
                            is_streaming=False,
                        ))
        if on_streaming_text:
            on_streaming_text(lambda _: None)
        on_message(message)
        return

    # dict — stream event
    msg_type = message.get("type")
    if msg_type == "stream_request_start":
        on_set_stream_mode("requesting")
        return

    event = message.get("event", {})
    event_type = event.get("type") if isinstance(event, dict) else None

    if event_type == "message_start":
        ttft = message.get("ttftMs")
        if ttft is not None and on_api_metrics:
            on_api_metrics({"ttftMs": ttft})
        return

    if event_type == "message_stop":
        on_set_stream_mode("tool-use")
        on_streaming_tool_uses(lambda _: [])
        return

    if event_type == "content_block_start":
        on_streaming_text and on_streaming_text(lambda _: None)
        cb = event.get("content_block", {}) if isinstance(event, dict) else {}
        cb_type = cb.get("type") if isinstance(cb, dict) else None
        if cb_type in ("thinking", "redacted_thinking"):
            on_set_stream_mode("thinking")
        elif cb_type == "text":
            on_set_stream_mode("responding")
        elif cb_type == "tool_use":
            on_set_stream_mode("tool-input")
            idx = event.get("index", 0)
            on_streaming_tool_uses(lambda prev: [*prev, StreamingToolUse(idx, cb, "")])
        else:
            on_set_stream_mode("tool-input")
        return

    if event_type == "content_block_delta":
        delta = event.get("delta", {}) if isinstance(event, dict) else {}
        delta_type = delta.get("type") if isinstance(delta, dict) else None
        if delta_type == "text_delta":
            text = delta.get("text", "")
            on_update_length(text)
            if on_streaming_text:
                on_streaming_text(lambda current: (current or "") + text)
        elif delta_type == "input_json_delta":
            partial = delta.get("partial_json", "")
            idx = event.get("index", 0)
            on_update_length(partial)
            def _update(prev: List[Any], _idx: int = idx, _partial: str = partial) -> List[Any]:
                return [
                    StreamingToolUse(
                        el.index, el.content_block,
                        el.unparsed_tool_input + _partial,
                    ) if el.index == _idx else el
                    for el in prev
                ]
            on_streaming_tool_uses(_update)
        elif delta_type == "thinking_delta":
            on_update_length(delta.get("thinking", ""))
        return

    if event_type in ("content_block_stop", "message_delta"):
        on_set_stream_mode("responding")
        return


# ---------------------------------------------------------------------------
# wrap_in_system_reminder / wrap_messages_in_system_reminder
# ---------------------------------------------------------------------------

def wrap_in_system_reminder(content: str) -> str:
    """Wrap content in <system-reminder> tags."""
    return f"<system-reminder>\n{content}\n</system-reminder>"


def wrap_messages_in_system_reminder(
    messages: List[UserMessage],
) -> List[UserMessage]:
    """Wrap all text content in user messages in <system-reminder> tags."""
    result = []
    for msg in messages:
        if isinstance(msg.content, str):
            result.append(UserMessage(**{
                **vars(msg),
                "content": wrap_in_system_reminder(msg.content),
            }))
        elif isinstance(msg.content, list):
            new_content = []
            for block in msg.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    new_content.append({**block, "text": wrap_in_system_reminder(block["text"])})
                else:
                    new_content.append(block)
            result.append(UserMessage(**{**vars(msg), "content": new_content}))
        else:
            result.append(msg)
    return result


# ---------------------------------------------------------------------------
# normalize_attachment_for_api — convert attachment to user messages
# ---------------------------------------------------------------------------

def normalize_attachment_for_api(attachment: Any) -> List[UserMessage]:
    """
    Convert an Attachment to a list of UserMessages for the API.
    Minimal Python port — complex attachment types emit placeholder messages.
    """
    if not isinstance(attachment, dict):
        return []

    att_type = attachment.get("type", "")

    _EMPTY_ATTACHMENT_TYPES = {
        "already_read_file", "command_permissions", "edited_image_file",
        "hook_cancelled", "hook_error_during_execution", "hook_non_blocking_error",
        "hook_system_message", "structured_output", "hook_permission_decision",
        "dynamic_skill",
    }
    if att_type in _EMPTY_ATTACHMENT_TYPES:
        return []

    _LEGACY_TYPES = {
        "autocheckpointing", "background_task_status", "todo",
        "task_progress", "ultramemory",
    }
    if att_type in _LEGACY_TYPES:
        return []

    if att_type == "edited_text_file":
        return wrap_messages_in_system_reminder([
            create_user_message(
                content=(
                    f"Note: {attachment.get('filename')} was modified, either by the user "
                    f"or by a linter. This change was intentional, so make sure to take it "
                    f"into account as you proceed (ie. don't revert it unless the user asks "
                    f"you to). Don't tell the user this, since they are already aware. Here "
                    f"are the relevant changes (shown with line numbers):\n{attachment.get('snippet', '')}"
                ),
                is_meta=True,
            )
        ])

    if att_type == "compact_file_reference":
        return wrap_messages_in_system_reminder([
            create_user_message(
                content=(
                    f"Note: {attachment.get('filename')} was read before the last "
                    "conversation was summarized, but the contents are too large to include. "
                    "Use the read tool if you need to access it."
                ),
                is_meta=True,
            )
        ])

    if att_type == "critical_system_reminder":
        return wrap_messages_in_system_reminder([
            create_user_message(content=attachment.get("content", ""), is_meta=True)
        ])

    if att_type == "relevant_memories":
        memories = attachment.get("memories", [])
        msgs = [
            create_user_message(
                content=f"{m.get('header', m.get('path', ''))}\n\n{m.get('content', '')}",
                is_meta=True,
            )
            for m in memories
        ]
        return wrap_messages_in_system_reminder(msgs)

    if att_type == "nested_memory":
        c = attachment.get("content", {})
        return wrap_messages_in_system_reminder([
            create_user_message(
                content=f"Contents of {c.get('path', '')}:\n\n{c.get('content', '')}",
                is_meta=True,
            )
        ])

    if att_type == "queued_command":
        prompt = attachment.get("prompt", "")
        origin = attachment.get("origin")
        is_meta_prop = origin is not None or attachment.get("isMeta") or None
        if isinstance(prompt, list):
            text_blocks = [b for b in prompt if isinstance(b, dict) and b.get("type") == "text"]
            text = "\n".join(b.get("text", "") for b in text_blocks)
            return wrap_messages_in_system_reminder([
                create_user_message(
                    content=[{"type": "text", "text": text}],
                    is_meta=is_meta_prop,
                    origin=origin,
                    uuid=attachment.get("source_uuid"),
                )
            ])
        return wrap_messages_in_system_reminder([
            create_user_message(
                content=str(prompt),
                is_meta=is_meta_prop,
                origin=origin,
                uuid=attachment.get("source_uuid"),
            )
        ])

    if att_type == "token_usage":
        return [
            create_user_message(
                content=wrap_in_system_reminder(
                    f"Token usage: {attachment.get('used')}/{attachment.get('total')}; "
                    f"{attachment.get('remaining')} remaining"
                ),
                is_meta=True,
            )
        ]

    if att_type == "budget_usd":
        return [
            create_user_message(
                content=wrap_in_system_reminder(
                    f"USD budget: ${attachment.get('used')}/${attachment.get('total')}; "
                    f"${attachment.get('remaining')} remaining"
                ),
                is_meta=True,
            )
        ]

    if att_type == "hook_blocking_error":
        be = attachment.get("blockingError", {})
        return [
            create_user_message(
                content=wrap_in_system_reminder(
                    f"{attachment.get('hookName')} hook blocking error from command: "
                    f'"{be.get("command")}": {be.get("blockingError")}'
                ),
                is_meta=True,
            )
        ]

    if att_type == "hook_success":
        hook_event = attachment.get("hookEvent", "")
        if hook_event not in ("SessionStart", "UserPromptSubmit"):
            return []
        content_text = attachment.get("content", "")
        if not content_text:
            return []
        return [
            create_user_message(
                content=wrap_in_system_reminder(
                    f"{attachment.get('hookName')} hook success: {content_text}"
                ),
                is_meta=True,
            )
        ]

    if att_type == "hook_additional_context":
        ctx = attachment.get("content", [])
        if not ctx:
            return []
        return [
            create_user_message(
                content=wrap_in_system_reminder(
                    f"{attachment.get('hookName')} hook additional context: {chr(10).join(ctx)}"
                ),
                is_meta=True,
            )
        ]

    if att_type == "hook_stopped_continuation":
        return [
            create_user_message(
                content=wrap_in_system_reminder(
                    f"{attachment.get('hookName')} hook stopped continuation: {attachment.get('message', '')}"
                ),
                is_meta=True,
            )
        ]

    if att_type == "compaction_reminder":
        return wrap_messages_in_system_reminder([
            create_user_message(
                content=(
                    "Auto-compact is enabled. When the context window is nearly full, older "
                    "messages will be automatically summarized so you can continue working "
                    "seamlessly. There is no need to stop or rush \u2014 you have unlimited "
                    "context through automatic compaction."
                ),
                is_meta=True,
            )
        ])

    if att_type == "date_change":
        return wrap_messages_in_system_reminder([
            create_user_message(
                content=(
                    f"The date has changed. Today's date is now {attachment.get('newDate')}. "
                    "DO NOT mention this to the user explicitly because they are already aware."
                ),
                is_meta=True,
            )
        ])

    if att_type == "todo_reminder":
        todos = attachment.get("content", [])
        todo_items = "\n".join(
            f"{i+1}. [{t.get('status')}] {t.get('content')}" for i, t in enumerate(todos)
        )
        msg = (
            "The TodoWrite tool hasn't been used recently. If you're working on tasks that "
            "would benefit from tracking progress, consider using the TodoWrite tool to track "
            "progress. Also consider cleaning up the todo list if has become stale and no "
            "longer matches what you are working on. Only use it if it's relevant to the "
            "current work. This is just a gentle reminder - ignore if not applicable. Make "
            "sure that you NEVER mention this reminder to the user\n"
        )
        if todo_items:
            msg += f"\n\nHere are the existing contents of your todo list:\n\n[{todo_items}]"
        return wrap_messages_in_system_reminder([
            create_user_message(content=msg, is_meta=True)
        ])

    if att_type == "plan_mode_exit":
        plan_ref = ""
        if attachment.get("planExists"):
            plan_ref = f" The plan file is located at {attachment.get('planFilePath')} if you need to reference it."
        content = f"## Exited Plan Mode\n\nYou have exited plan mode. You can now make edits, run tools, and take actions.{plan_ref}"
        return wrap_messages_in_system_reminder([
            create_user_message(content=content, is_meta=True)
        ])

    if att_type == "auto_mode_exit":
        return wrap_messages_in_system_reminder([
            create_user_message(
                content=(
                    "## Exited Auto Mode\n\nYou have exited auto mode. The user may now want "
                    "to interact more directly. You should ask clarifying questions when the "
                    "approach is ambiguous rather than making assumptions."
                ),
                is_meta=True,
            )
        ])

    if att_type == "diagnostics":
        files = attachment.get("files", [])
        if not files:
            return []
        summary = str(files)
        return wrap_messages_in_system_reminder([
            create_user_message(
                content=f"<new-diagnostics>The following new diagnostic issues were detected:\n\n{summary}</new-diagnostics>",
                is_meta=True,
            )
        ])

    if att_type == "task_status":
        status = attachment.get("status", "")
        description = attachment.get("description", "")
        task_id = attachment.get("taskId", "")
        if status == "killed":
            return [
                create_user_message(
                    content=wrap_in_system_reminder(
                        f'Task "{description}" ({task_id}) was stopped by the user.'
                    ),
                    is_meta=True,
                )
            ]
        if status == "running":
            parts = [f'Background agent "{description}" ({task_id}) is still running.']
            if attachment.get("deltaSummary"):
                parts.append(f"Progress: {attachment['deltaSummary']}")
            parts.append("Do NOT spawn a duplicate. You will be notified when it completes.")
            return [
                create_user_message(
                    content=wrap_in_system_reminder(" ".join(parts)),
                    is_meta=True,
                )
            ]
        # completed/failed
        parts = [
            f"Task {task_id}",
            f"(type: {attachment.get('taskType', '')})",
            f"(status: {status})",
            f"(description: {description})",
        ]
        if attachment.get("deltaSummary"):
            parts.append(f"Delta: {attachment['deltaSummary']}")
        if attachment.get("outputFilePath"):
            parts.append(f"Read the output file to retrieve the result: {attachment['outputFilePath']}")
        return [
            create_user_message(
                content=wrap_in_system_reminder(" ".join(parts)),
                is_meta=True,
            )
        ]

    # Generic fallback: produce a system-reminder with the content if available
    raw_content = attachment.get("content")
    if raw_content and isinstance(raw_content, str):
        return wrap_messages_in_system_reminder([
            create_user_message(content=raw_content, is_meta=True)
        ])

    return []


# ---------------------------------------------------------------------------
# System message constructors
# ---------------------------------------------------------------------------

def create_system_message(
    content: str,
    level: str,
    tool_use_id: Optional[str] = None,
    prevent_continuation: Optional[bool] = None,
) -> SystemMessage:
    """Create a SystemInformationalMessage."""
    extra: Dict[str, Any] = {}
    if prevent_continuation:
        extra["preventContinuation"] = True
    return SystemMessage(
        type="system",
        subtype="informational",
        content=content,
        level=level,
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        tool_use_id=tool_use_id,
        prevent_continuation=prevent_continuation,
        extra_data=extra,
    )


def create_permission_retry_message(commands: List[str]) -> SystemMessage:
    """Create a SystemPermissionRetryMessage."""
    return SystemMessage(
        type="system",
        subtype="permission_retry",
        content=f"Allowed {', '.join(commands)}",
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        extra_data={"commands": commands},
    )


def create_bridge_status_message(
    url: str,
    upgrade_nudge: Optional[str] = None,
) -> SystemMessage:
    """Create a SystemBridgeStatusMessage."""
    return SystemMessage(
        type="system",
        subtype="bridge_status",
        content=f"/remote-control is active. Code in CLI or at {url}",
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        extra_data={"url": url, "upgradeNudge": upgrade_nudge},
    )


def create_scheduled_task_fire_message(content: str) -> SystemMessage:
    """Create a SystemScheduledTaskFireMessage."""
    return SystemMessage(
        type="system",
        subtype="scheduled_task_fire",
        content=content,
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
    )


def create_stop_hook_summary_message(
    hook_count: int,
    hook_infos: List[Any],
    hook_errors: List[str],
    prevented_continuation: bool,
    stop_reason: Optional[str],
    has_output: bool,
    level: str,
    tool_use_id: Optional[str] = None,
    hook_label: Optional[str] = None,
    total_duration_ms: Optional[int] = None,
) -> SystemMessage:
    """Create a SystemStopHookSummaryMessage."""
    return SystemMessage(
        type="system",
        subtype="stop_hook_summary",
        content="",
        level=level,
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        tool_use_id=tool_use_id,
        extra_data={
            "hookCount": hook_count,
            "hookInfos": hook_infos,
            "hookErrors": hook_errors,
            "preventedContinuation": prevented_continuation,
            "stopReason": stop_reason,
            "hasOutput": has_output,
            "hookLabel": hook_label,
            "totalDurationMs": total_duration_ms,
        },
    )


def create_turn_duration_message(
    duration_ms: int,
    budget: Optional[Dict[str, Any]] = None,
    message_count: Optional[int] = None,
) -> SystemMessage:
    """Create a SystemTurnDurationMessage."""
    return SystemMessage(
        type="system",
        subtype="turn_duration",
        content="",
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        extra_data={
            "durationMs": duration_ms,
            "budgetTokens": budget.get("tokens") if budget else None,
            "budgetLimit": budget.get("limit") if budget else None,
            "budgetNudges": budget.get("nudges") if budget else None,
            "messageCount": message_count,
        },
    )


def create_away_summary_message(content: str) -> SystemMessage:
    """Create a SystemAwaySummaryMessage."""
    return SystemMessage(
        type="system",
        subtype="away_summary",
        content=content,
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
    )


def create_memory_saved_message(written_paths: List[str]) -> SystemMessage:
    """Create a SystemMemorySavedMessage."""
    return SystemMessage(
        type="system",
        subtype="memory_saved",
        content="",
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        extra_data={"writtenPaths": written_paths},
    )


def create_agents_killed_message() -> SystemMessage:
    """Create a SystemAgentsKilledMessage."""
    return SystemMessage(
        type="system",
        subtype="agents_killed",
        content="",
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
    )


def create_api_metrics_message(
    *,
    ttft_ms: int,
    otps: float,
    is_p50: Optional[bool] = None,
    hook_duration_ms: Optional[int] = None,
    turn_duration_ms: Optional[int] = None,
    tool_duration_ms: Optional[int] = None,
    classifier_duration_ms: Optional[int] = None,
    tool_count: Optional[int] = None,
    hook_count: Optional[int] = None,
    classifier_count: Optional[int] = None,
    config_write_count: Optional[int] = None,
) -> SystemMessage:
    """Create a SystemApiMetricsMessage."""
    return SystemMessage(
        type="system",
        subtype="api_metrics",
        content="",
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        extra_data={
            "ttftMs": ttft_ms,
            "otps": otps,
            "isP50": is_p50,
            "hookDurationMs": hook_duration_ms,
            "turnDurationMs": turn_duration_ms,
            "toolDurationMs": tool_duration_ms,
            "classifierDurationMs": classifier_duration_ms,
            "toolCount": tool_count,
            "hookCount": hook_count,
            "classifierCount": classifier_count,
            "configWriteCount": config_write_count,
        },
    )


def create_command_input_message(content: str) -> SystemMessage:
    """Create a SystemLocalCommandMessage."""
    return SystemMessage(
        type="system",
        subtype="local_command",
        content=content,
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
    )


def create_compact_boundary_message(
    trigger: str,
    pre_tokens: int,
    last_pre_compact_message_uuid: Optional[str] = None,
    user_context: Optional[str] = None,
    messages_summarized: Optional[int] = None,
) -> SystemMessage:
    """Create a SystemCompactBoundaryMessage."""
    extra: Dict[str, Any] = {
        "compactMetadata": {
            "trigger": trigger,
            "preTokens": pre_tokens,
            "userContext": user_context,
            "messagesSummarized": messages_summarized,
        }
    }
    if last_pre_compact_message_uuid:
        extra["logicalParentUuid"] = last_pre_compact_message_uuid
    return SystemMessage(
        type="system",
        subtype="compact_boundary",
        content="Conversation compacted",
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        extra_data=extra,
    )


def create_microcompact_boundary_message(
    trigger: str,
    pre_tokens: int,
    tokens_saved: int,
    compacted_tool_ids: List[str],
    cleared_attachment_uuids: List[str],
) -> SystemMessage:
    """Create a SystemMicrocompactBoundaryMessage."""
    return SystemMessage(
        type="system",
        subtype="microcompact_boundary",
        content="Context microcompacted",
        level="info",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        extra_data={
            "microcompactMetadata": {
                "trigger": trigger,
                "preTokens": pre_tokens,
                "tokensSaved": tokens_saved,
                "compactedToolIds": compacted_tool_ids,
                "clearedAttachmentUUIDs": cleared_attachment_uuids,
            }
        },
    )


def create_system_api_error_message(
    error: Any,
    retry_in_ms: int,
    retry_attempt: int,
    max_retries: int,
) -> SystemMessage:
    """Create a SystemAPIErrorMessage."""
    return SystemMessage(
        type="system",
        subtype="api_error",
        content=str(error),
        level="error",
        is_meta=False,
        timestamp=_now_iso(),
        uuid=str(_uuid_mod.uuid4()),
        extra_data={
            "error": error,
            "retryInMs": retry_in_ms,
            "retryAttempt": retry_attempt,
            "maxRetries": max_retries,
        },
    )


# ---------------------------------------------------------------------------
# compact boundary helpers
# ---------------------------------------------------------------------------

def is_compact_boundary_message(
    message: Union[Message, NormalizedMessage],
) -> bool:
    """Return True if the message is a compact boundary marker."""
    return isinstance(message, SystemMessage) and message.subtype == "compact_boundary"


def find_last_compact_boundary_index(messages: List[Any]) -> int:
    """
    Find the index of the last compact boundary marker.
    Returns -1 if none found.
    """
    for i in range(len(messages) - 1, -1, -1):
        if is_compact_boundary_message(messages[i]):
            return i
    return -1


def get_messages_after_last_compact_boundary(messages: List[Any]) -> List[Any]:
    """Return messages from the last compact boundary onward (inclusive)."""
    idx = find_last_compact_boundary_index(messages)
    if idx == -1:
        return messages
    return messages[idx:]


# ---------------------------------------------------------------------------
# filter_orphaned_thinking_only_messages
# ---------------------------------------------------------------------------

def _filter_orphaned_thinking_only_messages_flat(
    messages: List[Union[UserMessage, AssistantMessage]],
) -> List[Union[UserMessage, AssistantMessage]]:
    """
    Filter orphaned thinking-only assistant messages (internal helper for flat lists).
    """
    # Collect message IDs that have non-thinking content
    ids_with_non_thinking: Set[str] = set()
    for msg in messages:
        if not isinstance(msg, AssistantMessage):
            continue
        mid = (msg.message or {}).get("id") or msg.id
        content = msg.content if isinstance(msg.content, list) else []
        has_non_thinking = any(
            (isinstance(b, dict) and b.get("type") not in ("thinking", "redacted_thinking"))
            or (hasattr(b, "type") and b.type not in ("thinking", "redacted_thinking"))
            for b in content
        )
        if has_non_thinking:
            ids_with_non_thinking.add(mid)

    result = []
    for msg in messages:
        if not isinstance(msg, AssistantMessage):
            result.append(msg)
            continue
        mid = (msg.message or {}).get("id") or msg.id
        content = msg.content if isinstance(msg.content, list) else []
        if content and mid not in ids_with_non_thinking:
            # Only thinking/redacted_thinking blocks — potential orphan
            # Skip only if there IS a non-thinking sibling for same ID
            if any(
                isinstance(m, AssistantMessage)
                and ((m.message or {}).get("id") or m.id) == mid
                and m is not msg
                for m in messages
            ):
                continue
        result.append(msg)
    return result


def filter_orphaned_thinking_only_messages(
    messages: List[Message],
) -> List[Message]:
    """
    Filter orphaned thinking-only assistant messages.
    Prevents consecutive assistant messages with mismatched thinking block signatures
    causing API 400 errors.
    """
    # Collect message IDs that have non-thinking content
    ids_with_non_thinking: Set[str] = set()
    for msg in messages:
        if not isinstance(msg, AssistantMessage):
            continue
        mid = (msg.message or {}).get("id") or msg.id
        content = msg.content if isinstance(msg.content, list) else []
        has_non_thinking = any(
            (isinstance(b, dict) and b.get("type") not in ("thinking", "redacted_thinking"))
            or (hasattr(b, "type") and b.type not in ("thinking", "redacted_thinking"))
            for b in content
        )
        if has_non_thinking:
            ids_with_non_thinking.add(mid)

    result: List[Message] = []
    for msg in messages:
        if not isinstance(msg, AssistantMessage):
            result.append(msg)
            continue
        mid = (msg.message or {}).get("id") or msg.id
        content = msg.content if isinstance(msg.content, list) else []
        # All-thinking message with a non-thinking sibling => orphan, remove
        all_thinking = bool(content) and all(
            (isinstance(b, dict) and b.get("type") in ("thinking", "redacted_thinking"))
            or (hasattr(b, "type") and b.type in ("thinking", "redacted_thinking"))
            for b in content
        )
        if all_thinking and mid in ids_with_non_thinking:
            continue
        result.append(msg)
    return result


# ---------------------------------------------------------------------------
# Back-compat shims for original stub API
# ---------------------------------------------------------------------------

def get_message_text(message: Union[UserMessage, AssistantMessage]) -> str:
    """
    Extract all text blocks from a message as a single string.
    (Back-compat with original stub.)
    """
    parts: List[str] = []
    content = message.content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, TextBlock):
                parts.append(block.text)
    elif isinstance(content, str):
        return content
    return "\n".join(parts)


def normalize_messages_for_api_legacy(
    messages: List[Message],
) -> List[Dict[str, Any]]:
    """
    Back-compat shim: convert internal messages to Anthropic API dicts.
    """
    result: List[Dict[str, Any]] = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        if isinstance(msg, (UserMessage, AssistantMessage)):
            api_content: List[Any] = []
            for block in (msg.content if isinstance(msg.content, list) else []):
                if isinstance(block, dict):
                    api_content.append(block)
                elif hasattr(block, "__dict__"):
                    api_content.append(vars(block))
                else:
                    api_content.append({"type": "text", "text": str(block)})
            result.append({"role": msg.role, "content": api_content})
    return result

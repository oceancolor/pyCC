"""
Ported from: commands/rename/generateSessionName.ts

Utility function that asks the Claude Haiku model to generate a short
kebab-case session name from the current conversation transcript.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Stub helpers
# ---------------------------------------------------------------------------

def _extract_conversation_text(messages: List[Any]) -> Optional[str]:
    try:
        from claude_code.utils.session_title import extract_conversation_text  # type: ignore[import]
        return extract_conversation_text(messages)
    except ImportError:
        pass

    # Minimal fallback: concatenate text from message dicts
    parts: List[str] = []
    for msg in messages:
        if isinstance(msg, dict):
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text", ""))
    return " ".join(parts).strip() or None


def _extract_text_content(content: Any) -> str:
    try:
        from claude_code.utils.messages import extract_text_content  # type: ignore[import]
        return extract_text_content(content)
    except ImportError:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    return block.get("text", "")
        return ""


def _safe_parse_json(text: str) -> Optional[Any]:
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None


def _log_for_debugging(message: str, **kwargs) -> None:
    try:
        from claude_code.utils.debug import log_for_debugging  # type: ignore[import]
        log_for_debugging(message, **kwargs)
    except ImportError:
        pass


async def _query_haiku(
    system_prompt: List[str],
    user_prompt: str,
    signal: Optional[asyncio.Event],
) -> Optional[Dict[str, Any]]:
    """
    Call the Haiku model for a single-turn structured-output query.

    Returns the API response dict or None if unavailable.
    """
    try:
        from claude_code.services.api.claude import query_haiku  # type: ignore[import]
        result = await query_haiku(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            output_format={
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                    "additionalProperties": False,
                },
            },
            signal=signal,
            options={
                "query_source": "rename_generate_name",
                "agents": [],
                "is_non_interactive_session": False,
                "has_append_system_prompt": False,
                "mcp_tools": [],
            },
        )
        return result
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_session_name(
    messages: List[Any],
    signal: Optional[asyncio.Event] = None,
) -> Optional[str]:
    """
    Generate a short kebab-case session name for *messages*.

    The name is 2–4 words, e.g. ``"fix-login-bug"`` or ``"add-auth-feature"``.
    Returns ``None`` if the conversation has no useful text or if the API
    call fails.

    Parameters
    ----------
    messages:
        List of conversation messages (dicts with ``role`` and ``content``).
    signal:
        Optional cancellation signal; passed through to the API call.
    """
    conversation_text = _extract_conversation_text(messages)
    if not conversation_text:
        return None

    system_prompt = [
        "Generate a short kebab-case name (2-4 words) that captures the main topic "
        "of this conversation. Use lowercase words separated by hyphens. "
        'Examples: "fix-login-bug", "add-auth-feature", "refactor-api-client", '
        '"debug-test-failures". Return JSON with a "name" field.'
    ]

    try:
        result = await _query_haiku(
            system_prompt=system_prompt,
            user_prompt=conversation_text,
            signal=signal,
        )
        if result is None:
            return None

        message = result.get("message", {})
        content = _extract_text_content(message.get("content", ""))
        parsed = _safe_parse_json(content)

        if (
            parsed is not None
            and isinstance(parsed, dict)
            and "name" in parsed
            and isinstance(parsed["name"], str)
        ):
            return parsed["name"]

        return None

    except Exception as error:  # noqa: BLE001
        _log_for_debugging(
            f"generate_session_name failed: {error}",
            level="error",
        )
        return None

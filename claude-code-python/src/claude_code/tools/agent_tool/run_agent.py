"""
Core agent run loop.
Ported from AgentTool/runAgent.ts (973 lines → core loop + filterIncompleteToolCalls).

Key exports:
- run_agent(...)   — async generator, full agent execution loop
- filter_incomplete_tool_calls(messages) — filter orphaned tool calls
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 50


async def run_agent(
    agent_id: str,
    system_prompt: str,
    messages: List[dict],
    tools: Optional[List[Any]] = None,
    tool_use_context: Any = None,
    can_use_tool: Any = None,
    signal: Any = None,
    max_iterations: int = MAX_AGENT_ITERATIONS,
) -> AsyncIterator[dict]:
    """
    Core agent execution loop.

    Mirrors runAgent() in runAgent.ts (lines 248–).
    Streams events:
      - {"type": "assistant_message", "content": [...], "iteration": N}
      - {"type": "tool_result",       "tool_name": str, "result": Any, "iteration": N}
      - {"type": "final_response",    "content": [...], "iterations": N}
      - {"type": "max_iterations_reached", "iterations": N}
    """
    from claude_code.services.api.claude import query_model_without_streaming

    iteration = 0
    current_messages = list(messages)

    while iteration < max_iterations:
        iteration += 1

        result = await query_model_without_streaming(
            messages=current_messages,
            system_prompt=[system_prompt] if system_prompt else [],
            tools=_serialize_tools(tools),
            options={"max_tokens": 4096},
            signal=signal,
        )

        content = result.get("content", [])
        stop_reason = result.get("stop_reason")

        yield {
            "type": "assistant_message",
            "content": content,
            "iteration": iteration,
        }

        # Collect tool_use blocks from the response
        tool_uses = [
            b for b in content
            if isinstance(b, dict) and b.get("type") == "tool_use"
        ]

        # No tool calls, or model finished — this is the final response
        if not tool_uses or stop_reason == "end_turn":
            yield {
                "type": "final_response",
                "content": content,
                "iterations": iteration,
            }
            return

        # Execute each tool call and collect results
        tool_results = []
        for tu in tool_uses:
            tool_name = tu.get("name", "")
            tool_input = tu.get("input", {})
            tool_use_id = tu.get("id", "")
            try:
                result_content = await _execute_tool(
                    tool_name, tool_input, tools, tool_use_context
                )
            except Exception as exc:
                logger.debug("Tool %s raised: %s", tool_name, exc)
                result_content = {"type": "error", "error": str(exc)}

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": str(result_content),
            })
            yield {
                "type": "tool_result",
                "tool_name": tool_name,
                "result": result_content,
                "iteration": iteration,
            }

        # Append assistant turn + user turn with tool results
        current_messages.append({"role": "assistant", "content": content})
        current_messages.append({"role": "user", "content": tool_results})

    yield {"type": "max_iterations_reached", "iterations": iteration}


def filter_incomplete_tool_calls(messages: List[dict]) -> List[dict]:
    """
    Filter out assistant messages that contain tool calls without corresponding
    tool results.  Mirrors filterIncompleteToolCalls() in runAgent.ts (line 866).

    An "incomplete" tool call is a ``tool_use`` block in an assistant message
    whose ``id`` does not appear in any ``tool_result`` block in a subsequent
    user message.  Keeping such orphaned tool calls would cause API errors when
    the messages are forwarded.

    Args:
        messages: List of message dicts with ``type`` and ``message`` keys
                  (the internal Message type used throughout the port), OR
                  plain {"role": "assistant"/"user", "content": [...]} dicts.

    Returns:
        Filtered list with orphaned-tool-call assistant messages removed.
    """
    # --- collect all tool_use_ids that have a corresponding result ---
    tool_use_ids_with_results: set[str] = set()

    for message in messages:
        # Support both internal Message envelope and raw API message formats
        msg_type = _get_message_type(message)
        msg_content = _get_message_content(message)

        if msg_type == "user" and isinstance(msg_content, list):
            for block in msg_content:
                if (
                    isinstance(block, dict)
                    and block.get("type") == "tool_result"
                    and block.get("tool_use_id")
                ):
                    tool_use_ids_with_results.add(block["tool_use_id"])

    # --- drop assistant messages with orphaned tool_use blocks ---
    filtered: List[dict] = []
    for message in messages:
        msg_type = _get_message_type(message)
        msg_content = _get_message_content(message)

        if msg_type == "assistant" and isinstance(msg_content, list):
            has_incomplete = any(
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("id")
                and block["id"] not in tool_use_ids_with_results
                for block in msg_content
            )
            if has_incomplete:
                continue  # drop this message

        filtered.append(message)

    return filtered


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_message_type(message: dict) -> Optional[str]:
    """Return the logical message type from either message format."""
    # Internal envelope: {"type": "assistant", "message": {...}}
    if "type" in message and message["type"] in ("assistant", "user", "progress", "system"):
        return message["type"]
    # Raw API format: {"role": "assistant", "content": [...]}
    role = message.get("role")
    if role in ("assistant", "user"):
        return role
    return None


def _get_message_content(message: dict) -> Any:
    """Return the content list from either message format."""
    # Internal envelope: message["message"]["content"]
    inner = message.get("message")
    if isinstance(inner, dict):
        return inner.get("content", [])
    # Raw API / simplified format: message["content"]
    return message.get("content", [])


def _serialize_tools(tools: Optional[List[Any]]) -> List[dict]:
    """Serialize tool objects to the API dict format."""
    if not tools:
        return []
    result = []
    for t in tools:
        schema = (
            t.input_schema()
            if callable(getattr(t, "input_schema", None))
            else {}
        )
        result.append({
            "name": t.name,
            "description": t.description or "",
            "input_schema": schema,
        })
    return result


async def _execute_tool(
    name: str,
    input_data: dict,
    tools: Optional[List[Any]],
    context: Any,
) -> Any:
    """Find and invoke a tool by name."""
    if not tools:
        return f"Tool {name} not found"
    for t in tools:
        if getattr(t, "name", None) == name:
            return await t.call(input_data, context)
    return f"Tool {name} not found"

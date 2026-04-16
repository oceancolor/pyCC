"""
Tool loop / agent query service
原始 TS: src/query.ts (simplified port)

This is the main "agentic loop" — sends messages to Claude, processes tool calls,
and iterates until a final text response or stop condition.
"""
from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Callable, Optional

from claude_code.tool import Tool, ToolUseContext, get_empty_tool_use_context
from claude_code.utils.messages import (
    UserMessage,
    AssistantMessage,
    normalize_messages_for_api,
    create_user_message,
    Message,
)
from claude_code.utils.errors import AbortError

# Max tool iterations before forcing a stop
MAX_TOOL_ITERATIONS = 50


@dataclass
class QueryOptions:
    model: str = ""
    system_prompt: Optional[str] = None
    tools: list[Tool] = field(default_factory=list)
    max_tokens: int = 8192
    max_iterations: int = MAX_TOOL_ITERATIONS
    abort_signal: Optional[asyncio.Event] = None


@dataclass
class QueryResult:
    messages: list[Message]
    stop_reason: str = ""
    usage: Optional[dict[str, int]] = None
    model: str = ""
    error: Optional[str] = None


def _tools_to_api_schema(tools: list[Tool]) -> list[dict[str, Any]]:
    """Convert Tool instances to Anthropic API tool definitions."""
    return [
        {
            "name": t.name,
            "description": asyncio.get_event_loop().run_until_complete(t.description())
            if asyncio.get_event_loop().is_running()
            else t.name,  # fallback
            "input_schema": t.input_schema(),
        }
        for t in tools
    ]


async def _build_tool_schemas(tools: list[Tool]) -> list[dict[str, Any]]:
    """Build tool schemas asynchronously."""
    schemas = []
    for t in tools:
        schemas.append({
            "name": t.name,
            "description": await t.description(),
            "input_schema": t.input_schema(),
        })
    return schemas


async def run_query(
    initial_messages: list[Message],
    options: QueryOptions,
    *,
    context: Optional[ToolUseContext] = None,
    on_chunk: Optional[Callable[[str], None]] = None,
) -> QueryResult:
    """
    Run the agent query loop.
    原始 TS: query() function in query.ts

    Sends messages to Claude, handles tool calls, iterates until done.
    """
    from claude_code.services.api import get_anthropic_client

    ctx = context or get_empty_tool_use_context()
    tool_by_name: dict[str, Tool] = {t.name: t for t in options.tools}

    messages: list[Message] = list(initial_messages)
    api_messages = normalize_messages_for_api(messages)

    tool_schemas = await _build_tool_schemas(options.tools)

    try:
        client = get_anthropic_client(model=options.model)
    except (ValueError, NotImplementedError) as e:
        return QueryResult(messages=messages, error=str(e))

    iterations = 0

    while iterations < options.max_iterations:
        iterations += 1

        # Check abort
        if options.abort_signal and options.abort_signal.is_set():
            raise AbortError("Query aborted")

        # Call API
        kwargs: dict[str, Any] = {
            "model": options.model,
            "max_tokens": options.max_tokens,
            "messages": api_messages,
        }
        if options.system_prompt:
            kwargs["system"] = options.system_prompt
        if tool_schemas:
            kwargs["tools"] = tool_schemas  # type: ignore

        response = client.messages.create(**kwargs)

        stop_reason = response.stop_reason or ""
        model = response.model

        # Build assistant message
        assistant_content: list[Any] = []
        for block in response.content:
            if hasattr(block, "model_dump"):
                assistant_content.append(block.model_dump())
            else:
                assistant_content.append({"type": "text", "text": str(block)})

        assistant_msg = AssistantMessage(
            content=assistant_content,
            stop_reason=stop_reason,
            model=model,
        )
        messages.append(assistant_msg)
        api_messages.append({"role": "assistant", "content": assistant_content})

        # If not a tool use, we're done
        if stop_reason != "tool_use":
            if on_chunk:
                for block in assistant_content:
                    if block.get("type") == "text":
                        on_chunk(block.get("text", ""))
            break

        # Process tool calls
        tool_results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", "") == "tool_use":
                tool_name = block.name
                tool_input = block.input or {}
                tool_use_id = block.id

                tool = tool_by_name.get(tool_name)
                if tool is None:
                    result = {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": f"Error: Unknown tool: {tool_name}",
                        "is_error": True,
                    }
                else:
                    try:
                        output = await tool.call(tool_input, ctx)
                        # Normalize output
                        if isinstance(output, dict):
                            if output.get("type") == "text":
                                content = output.get("text", "")
                            else:
                                content = json.dumps(output)
                        elif isinstance(output, str):
                            content = output
                        else:
                            content = json.dumps(output)
                        result = {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": content,
                        }
                    except Exception as e:
                        result = {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": f"Error: {e}",
                            "is_error": True,
                        }

                tool_results.append(result)

        if not tool_results:
            break  # No tool calls even though stop_reason == 'tool_use', something wrong

        # Add tool results as user message
        user_msg_content = tool_results
        user_msg = UserMessage(content=user_msg_content)
        messages.append(user_msg)
        api_messages.append({"role": "user", "content": user_msg_content})

    usage_data = None
    if hasattr(response, "usage") and response.usage:
        usage_data = {
            "input_tokens": getattr(response.usage, "input_tokens", 0),
            "output_tokens": getattr(response.usage, "output_tokens", 0),
        }

    return QueryResult(
        messages=messages,
        stop_reason=stop_reason if "stop_reason" in dir() else "",
        usage=usage_data,
        model=model if "model" in dir() else options.model,
    )

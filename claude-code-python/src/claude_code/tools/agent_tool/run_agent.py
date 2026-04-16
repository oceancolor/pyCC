"""
Core agent run loop.
Ported from AgentTool/runAgent.ts (973 lines → core loop).
"""
from __future__ import annotations
import asyncio
import os
from typing import Any, AsyncIterator, Dict, List, Optional

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
    Streams events: thinking, tool_use, tool_result, final_response.
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

        yield {"type": "assistant_message", "content": content,
               "iteration": iteration}

        # Check for tool use
        tool_uses = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not tool_uses or stop_reason == "end_turn":
            yield {"type": "final_response", "content": content,
                   "iterations": iteration}
            return

        # Execute tools
        tool_results = []
        for tu in tool_uses:
            tool_name = tu.get("name", "")
            tool_input = tu.get("input", {})
            try:
                result_content = await _execute_tool(tool_name, tool_input, tools, tool_use_context)
            except Exception as e:
                result_content = {"type": "error", "error": str(e)}
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.get("id", ""),
                "content": str(result_content),
            })
            yield {"type": "tool_result", "tool_name": tool_name,
                   "result": result_content, "iteration": iteration}

        current_messages.append({"role": "assistant", "content": content})
        current_messages.append({"role": "user", "content": tool_results})

    yield {"type": "max_iterations_reached", "iterations": iteration}


def _serialize_tools(tools: Optional[List[Any]]) -> List[dict]:
    if not tools:
        return []
    result = []
    for t in tools:
        schema = t.input_schema() if callable(getattr(t, "input_schema", None)) else {}
        result.append({"name": t.name, "description": t.description or "", "input_schema": schema})
    return result


async def _execute_tool(name: str, input_data: dict, tools: Optional[List[Any]],
                         context: Any) -> Any:
    if not tools:
        return f"Tool {name} not found"
    for t in tools:
        if getattr(t, "name", None) == name:
            return await t.call(input_data, context)
    return f"Tool {name} not found"

"""AgentTool package. Ported from tools/AgentTool/AgentTool.ts

Provides subagent-spawning and task-delegation tools.
"""
from __future__ import annotations

from typing import Any, Optional

from claude_code.constants.tools import AGENT_TOOL_NAME
from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext
from claude_code.tools.agent_tool.constants import (
    LEGACY_AGENT_TOOL_NAME,
    VERIFICATION_AGENT_TYPE,
    ONE_SHOT_BUILTIN_AGENT_TYPES,
)


class AgentTool(Tool):
    """Launches a subagent to handle complex subtasks.

    Ported from tools/AgentTool/AgentTool.ts
    """

    name = AGENT_TOOL_NAME
    search_hint = "run a subagent to complete a complex task"
    max_result_size_chars = 200_000

    async def description(self) -> str:
        return "Launch a new agent that has access to tools to complete a specific task."

    async def prompt(self) -> str:
        return """Launch a new agent that has access to tools to complete a specific task.

Use this when you need to:
- Run long tasks in parallel
- Complete a well-defined subtask with specific scope
- Delegate work that would overload the current context

The agent will run independently and report back results."""

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The task for the subagent",
                },
                "description": {
                    "type": "string",
                    "description": "Short description of the subagent task",
                },
            },
            "required": ["prompt"],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        """Spawn a subagent for the given task.

        This is a stub implementation; full subagent spawning relies on
        ``claude_code.tools.agent_tool.run_agent.run_agent``.
        """
        try:
            from claude_code.tools.agent_tool.run_agent import run_agent  # type: ignore
            return await run_agent(input_data, context)
        except Exception:
            return {
                "type": "text",
                "text": "[AgentTool stub: subagent spawning is not yet fully wired up]",
            }


class SleepTool(Tool):
    """Sleeps for a specified duration.

    Ported from tools/SleepTool/
    """

    name = "Sleep"
    search_hint = "pause execution for a specified time"

    async def description(self) -> str:
        return "Sleeps for a given number of milliseconds."

    async def prompt(self) -> str:
        return "Use this tool to pause execution for a specified number of milliseconds."

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "duration_ms": {
                    "type": "integer",
                    "description": "Duration to sleep in milliseconds",
                    "minimum": 0,
                    "maximum": 60000,
                },
            },
            "required": ["duration_ms"],
        }

    async def call(
        self,
        input_data: dict[str, Any],
        context: ToolUseContext,
    ) -> dict[str, Any]:
        import asyncio
        duration_ms = int(input_data.get("duration_ms", 0))
        duration_ms = max(0, min(duration_ms, 60000))
        await asyncio.sleep(duration_ms / 1000.0)
        return {"type": "text", "text": f"Slept for {duration_ms}ms"}


__all__ = [
    "AgentTool",
    "SleepTool",
    "AGENT_TOOL_NAME",
    "LEGACY_AGENT_TOOL_NAME",
    "VERIFICATION_AGENT_TYPE",
    "ONE_SHOT_BUILTIN_AGENT_TYPES",
]

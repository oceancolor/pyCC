"""
Streaming tool executor.
Ported from services/tools/StreamingToolExecutor.ts (530 lines → core).
"""
from __future__ import annotations
import asyncio
from typing import Any, AsyncIterator, List, Optional


class StreamingToolExecutor:
    """Execute tools in streaming mode, yielding intermediate progress events."""

    def __init__(self, tools: List[Any], context: Any):
        self.tools = tools
        self.context = context

    def find_tool(self, name: str) -> Optional[Any]:
        return next((t for t in self.tools if getattr(t, "name", "") == name), None)

    async def execute(
        self,
        tool_use_id: str,
        tool_name: str,
        tool_input: dict,
        signal: Any = None,
    ) -> AsyncIterator[dict]:
        from claude_code.services.tools.tool_execution import run_tool_use
        tool = self.find_tool(tool_name)
        if not tool:
            yield {"type": "error", "tool_use_id": tool_use_id,
                   "error": f"Tool not found: {tool_name}"}
            return
        async for event in run_tool_use(tool, tool_input, self.context, signal=signal):
            yield {**event, "tool_use_id": tool_use_id}

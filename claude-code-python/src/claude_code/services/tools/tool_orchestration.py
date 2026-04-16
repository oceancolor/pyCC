"""
Tool orchestration — deduplication, scheduling, batching.
Ported from services/tools/toolOrchestration.ts (188 lines).
"""
from __future__ import annotations
import asyncio
from typing import Any, Dict, List, Optional

_pending_tools: Dict[str, asyncio.Task] = {}


def get_pending_tool_count() -> int:
    return len(_pending_tools)


async def orchestrate_tool_batch(
    tool_uses: List[dict],
    tools: List[Any],
    context: Any,
) -> List[dict]:
    """Run multiple tool uses concurrently and collect results."""
    from claude_code.services.tools.tool_execution import run_tool_use

    async def _run_one(tu: dict) -> dict:
        tool_name = tu.get("name", "")
        tool_input = tu.get("input", {})
        tool_obj = next((t for t in tools if getattr(t, "name", "") == tool_name), None)
        if not tool_obj:
            return {"tool_use_id": tu.get("id", ""), "error": f"Tool not found: {tool_name}"}
        result = None
        async for event in run_tool_use(tool_obj, tool_input, context):
            if event.get("type") == "tool_result":
                result = event.get("result")
        return {"tool_use_id": tu.get("id", ""), "result": result}

    results = await asyncio.gather(*[_run_one(tu) for tu in tool_uses])
    return list(results)


# services/tools/streaming_tool_executor.py

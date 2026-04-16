"""AgentTool utilities. Ported from AgentTool/agentToolUtils.ts"""
from __future__ import annotations
import asyncio
from typing import Any, Callable, Optional

async def run_async_agent_lifecycle(
    agent_id: str,
    run_fn: Callable,
    on_complete: Optional[Callable] = None,
    on_error: Optional[Callable] = None,
) -> Any:
    """Run an agent lifecycle asynchronously."""
    try:
        result = await run_fn()
        if on_complete:
            await on_complete(result)
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        if on_error:
            await on_error(e)
        raise

def generate_agent_id(prefix: str = "agent") -> str:
    import uuid
    return f"{prefix}:{uuid.uuid4()}"

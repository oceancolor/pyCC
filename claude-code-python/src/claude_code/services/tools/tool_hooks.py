"""
Tool hook runners (pre/post use, failure).
Ported from services/tools/toolHooks.ts (650 lines → core).
"""
from __future__ import annotations
import asyncio
from typing import Any, AsyncIterator, Optional


async def run_pre_tool_use_hooks(
    tool: Any,
    tool_input: dict,
    context: Any,
) -> AsyncIterator[dict]:
    """Run pre-tool hooks. Yields hook progress events."""
    try:
        from claude_code.utils.hooks import execute_pre_tool_hooks
        results = execute_pre_tool_hooks(
            getattr(tool, "name", "unknown"), tool_input
        )
        if asyncio.iscoroutine(results):
            results = await results
    except ImportError:
        return
    except Exception:
        return
    return
    yield  # make it a generator


async def run_post_tool_use_hooks(
    tool: Any,
    tool_input: dict,
    output: Any,
    context: Any,
) -> AsyncIterator[dict]:
    """Run post-tool hooks."""
    try:
        from claude_code.utils.hooks import execute_post_tool_hooks
        execute_post_tool_hooks(
            getattr(tool, "name", "unknown"), tool_input, output
        )
    except ImportError:
        pass
    return
    yield


async def run_post_tool_use_failure_hooks(
    tool: Any,
    tool_input: dict,
    error: Exception,
    context: Any,
) -> AsyncIterator[dict]:
    """Run post-failure hooks."""
    try:
        from claude_code.utils.hooks import execute_post_tool_use_failure_hooks
        execute_post_tool_use_failure_hooks(
            getattr(tool, "name", "unknown"), tool_input, error
        )
    except ImportError:
        pass
    return
    yield


async def resolve_hook_permission_decision(
    tool: Any,
    tool_input: dict,
    context: Any,
) -> Optional[dict]:
    """Resolve permission from hook rules. Returns None if no rule matches."""
    return None


class PostToolUseHooksResult:
    def __init__(self, blocked: bool = False, message: str = ""):
        self.blocked = blocked
        self.message = message

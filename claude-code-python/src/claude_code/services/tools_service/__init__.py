"""Tools service.

Orchestrates tool execution within agent turns: running tools in parallel
or sequentially, applying pre/post-use hooks, handling permission checks,
and streaming progress updates to the UI.

Ported from: src/services/toolsService/ (TypeScript)

Usage::

    from claude_code.services.tools_service import (
        TrackedTool,
        MessageUpdate,
        orchestrate_tools,
        PostToolUseHooksResult,
        resolve_hook_permission_decision,
        classify_tool_error,
    )
"""
from __future__ import annotations

from claude_code.services.tools_service.streaming_tool_executor import TrackedTool, MessageUpdate
from claude_code.services.tools_service.tool_orchestration import orchestrate_tools
from claude_code.services.tools_service.tool_hooks import (
    PostToolUseHooksResult,
    resolve_hook_permission_decision,
)
from claude_code.services.tools_service.tool_execution import classify_tool_error

__all__ = [
    "TrackedTool",
    "MessageUpdate",
    "orchestrate_tools",
    "PostToolUseHooksResult",
    "resolve_hook_permission_decision",
    "classify_tool_error",
]

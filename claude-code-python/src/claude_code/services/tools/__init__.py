"""Tools module exports."""
from claude_code.services.tools.streaming_tool_executor import StreamingToolExecutor
from claude_code.services.tools.tool_hooks import (
    run_pre_tool_use_hooks,
    run_post_tool_use_hooks,
    run_post_tool_use_failure_hooks,
    resolve_hook_permission_decision,
    PostToolUseHooksResult,
)
from claude_code.services.tools.tool_orchestration import (
    orchestrate_tool_batch,
    get_pending_tool_count,
)

__all__ = [
    "StreamingToolExecutor",
    "run_pre_tool_use_hooks",
    "run_post_tool_use_hooks",
    "run_post_tool_use_failure_hooks",
    "resolve_hook_permission_decision",
    "PostToolUseHooksResult",
    "orchestrate_tool_batch",
    "get_pending_tool_count",
]

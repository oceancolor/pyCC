"""RemoteTriggerTool package.

Re-exports RemoteTriggerTool and its canonical name constant.

RemoteTriggerTool sends an event to a remote Claude Code session,
allowing one session to trigger actions in another.  This is used
for cross-session coordination in multi-agent workflows.

Ported from: tools/RemoteTriggerTool/ (TypeScript)

Usage::

    from claude_code.tools.remote_trigger_tool import (
        RemoteTriggerTool,
        REMOTE_TRIGGER_TOOL_NAME,
    )
"""
from __future__ import annotations

from claude_code.tools.remote_trigger_tool.remote_trigger_tool import (
    RemoteTriggerTool,
    REMOTE_TRIGGER_TOOL_NAME,
)

__all__ = [
    "RemoteTriggerTool",
    "REMOTE_TRIGGER_TOOL_NAME",
]

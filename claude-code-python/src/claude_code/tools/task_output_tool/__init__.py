"""TaskOutputTool package.

Re-exports the TaskOutputTool class from its implementation module.

TaskOutputTool sends an output message from a running background task back
to the session that created it.  This is the primary mechanism for a
background task to communicate progress or partial results to the parent
session without terminating.

Background tasks call this tool periodically to report status; the parent
session can read these messages to decide whether to foreground the task.

Ported from: tools/TaskOutputTool/ (TypeScript)

Usage::

    from claude_code.tools.task_output_tool import TaskOutputTool
"""
from __future__ import annotations

from claude_code.tools.task_output_tool.task_output_tool import TaskOutputTool

__all__ = ["TaskOutputTool"]

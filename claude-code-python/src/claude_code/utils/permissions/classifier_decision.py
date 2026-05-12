"""
Classifier decision - tools that are safe and don't need classifier checking.
"""

from __future__ import annotations

from typing import Set

# Tools that are safe and don't need any classifier checking.
SAFE_AUTO_MODE_ALLOWLISTED_TOOLS: Set[str] = {
    # Read-only file operations
    "FileReadTool",
    # Search / read-only
    "GrepTool",
    "GlobTool",
    "LSPTool",
    "ToolSearchTool",
    "ListMcpResourcesTool",
    "ReadMcpResourceTool",
    # Task management (metadata only)
    "TodoWriteTool",
    "TaskCreateTool",
    "TaskGetTool",
    "TaskUpdateTool",
    "TaskListTool",
    "TaskStopTool",
    "TaskOutputTool",
    # Plan mode / UI
    "AskUserQuestionTool",
    "EnterPlanModeTool",
    "ExitPlanModeTool",
    # Swarm coordination
    "TeamCreateTool",
    "TeamDeleteTool",
    "SendMessageTool",
    # Misc safe
    "SleepTool",
    # Internal classifier tool
    "YoloClassifierTool",
}


def is_auto_mode_allowlisted_tool(tool_name: str) -> bool:
    """Check if a tool is in the auto mode safe allowlist."""
    return tool_name in SAFE_AUTO_MODE_ALLOWLISTED_TOOLS

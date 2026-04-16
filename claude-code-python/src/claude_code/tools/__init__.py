"""
Tools package
原始 TS: src/tools/
"""
from claude_code.tools.agent_tool import AgentTool, SleepTool
from claude_code.tools.bash_tool import BashTool
from claude_code.tools.file_edit_tool import FileEditTool
from claude_code.tools.file_move_tool import FileMoveTool
from claude_code.tools.file_read_tool import FileReadTool
from claude_code.tools.file_write_tool import FileWriteTool
from claude_code.tools.glob_tool import GlobTool
from claude_code.tools.grep_tool import GrepTool
from claude_code.tools.notebook_edit_tool import NotebookEditTool
from claude_code.tools.notebook_read_tool import NotebookReadTool
from claude_code.tools.task_tool import (
    TaskCreateTool,
    TaskGetTool,
    TaskListTool,
    TaskStopTool,
    TaskUpdateTool,
)
from claude_code.tools.todo_read_tool import TodoReadTool
from claude_code.tools.todo_write_tool import TodoWriteTool
from claude_code.tools.tool_executor import ToolExecutor
from claude_code.tools.tool_registry import ToolRegistry, build_default_registry
from claude_code.tools.web_fetch_tool import WebFetchTool
from claude_code.tools.web_search_tool import WebSearchTool

__all__ = [
    "AgentTool",
    "BashTool",
    "FileEditTool",
    "FileMoveTool",
    "FileReadTool",
    "FileWriteTool",
    "GlobTool",
    "GrepTool",
    "NotebookEditTool",
    "NotebookReadTool",
    "SleepTool",
    "TaskCreateTool",
    "TaskGetTool",
    "TaskListTool",
    "TaskStopTool",
    "TaskUpdateTool",
    "TodoReadTool",
    "TodoWriteTool",
    "ToolExecutor",
    "ToolRegistry",
    "WebFetchTool",
    "WebSearchTool",
    "build_default_registry",
    "get_default_tools",
]


def get_default_tools() -> list:
    """Return the default set of tools for the agent loop."""
    return [
        BashTool(),
        FileReadTool(),
        FileEditTool(),
        FileWriteTool(),
        FileMoveTool(),
        GrepTool(),
        GlobTool(),
        TodoReadTool(),
        TodoWriteTool(),
        WebFetchTool(),
        NotebookEditTool(),
        NotebookReadTool(),
        TaskCreateTool(),
        TaskGetTool(),
        TaskListTool(),
        TaskStopTool(),
        TaskUpdateTool(),
    ]

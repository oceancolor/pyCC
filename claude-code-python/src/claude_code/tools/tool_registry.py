# 原始 TS: tools/ (聚合所有工具的注册表)
"""
tool_registry.py — 工具注册表，维护 name → tool 实例的映射。

用法：
    registry = ToolRegistry()
    registry.register(BashTool())
    tool = registry.get("Bash")
"""

from __future__ import annotations

from typing import Any

from ..tool import Tool as ToolBase


class ToolRegistry:
    """Central registry mapping tool names to tool instances."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolBase] = {}

    def register(self, tool: ToolBase) -> None:
        """Register a tool by its name."""
        if tool.name in self._tools:
            raise ValueError(f"Tool already registered: {tool.name!r}")
        self._tools[tool.name] = tool

    def register_many(self, tools: list[ToolBase]) -> None:
        """Register multiple tools at once."""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> ToolBase | None:
        """Return the tool with the given name, or None if not found."""
        return self._tools.get(name)

    def get_or_raise(self, name: str) -> ToolBase:
        """Return the tool with the given name, raising KeyError if not found."""
        tool = self._tools.get(name)
        if tool is None:
            available = sorted(self._tools.keys())
            raise KeyError(
                f"Unknown tool: {name!r}. Available: {available}"
            )
        return tool

    def all_tools(self) -> list[ToolBase]:
        """Return all registered tools."""
        return list(self._tools.values())

    def names(self) -> list[str]:
        """Return all registered tool names."""
        return sorted(self._tools.keys())

    def as_api_schemas(self) -> list[dict[str, Any]]:
        """
        Return all tools as Anthropic API-compatible tool definitions.

        Format::
            [
                {
                    "name": "Bash",
                    "description": "...",
                    "input_schema": {...},
                },
                ...
            ]
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema,
            }
            for tool in self._tools.values()
        ]

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        return f"ToolRegistry(tools={self.names()})"


def build_default_registry() -> ToolRegistry:
    """
    Build and return a ToolRegistry pre-populated with all default tools.

    Import here (not at module level) to avoid circular imports.
    """
    from .agent_tool import AgentTool, SleepTool
    from .bash_tool import BashTool
    from .file_edit_tool import FileEditTool
    from .file_move_tool import FileMoveTool
    from .file_read_tool import FileReadTool
    from .file_write_tool import FileWriteTool
    from .glob_tool import GlobTool
    from .grep_tool import GrepTool
    from .notebook_edit_tool import NotebookEditTool
    from .notebook_read_tool import NotebookReadTool
    from .task_tool import (
        TaskCreateTool,
        TaskGetTool,
        TaskListTool,
        TaskStopTool,
        TaskUpdateTool,
    )
    from .todo_read_tool import TodoReadTool
    from .todo_write_tool import TodoWriteTool
    from .web_fetch_tool import WebFetchTool
    from .web_search_tool import WebSearchTool

    registry = ToolRegistry()
    registry.register_many([
        AgentTool(),
        BashTool(),
        FileEditTool(),
        FileMoveTool(),
        FileReadTool(),
        FileWriteTool(),
        GlobTool(),
        GrepTool(),
        NotebookEditTool(),
        NotebookReadTool(),
        SleepTool(),
        TaskCreateTool(),
        TaskGetTool(),
        TaskListTool(),
        TaskStopTool(),
        TaskUpdateTool(),
        TodoReadTool(),
        TodoWriteTool(),
        WebFetchTool(),
        WebSearchTool(),
    ])
    return registry

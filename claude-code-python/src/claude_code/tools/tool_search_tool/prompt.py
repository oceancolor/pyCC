"""ToolSearchTool prompt. Ported from ToolSearchTool/prompt.ts"""
from __future__ import annotations

DESCRIPTION = "Search for available tools by keyword or capability"

PROMPT = """Search for available tools matching a keyword or capability description.

## When to Use

- When you're not sure which tool to use for a task
- When you want to discover MCP-provided tools for a specific purpose
- When you know what you want to do but don't know the tool name

## Usage

Provide a natural language query describing what you want to do. The tool will return a list of matching tools with their descriptions.

## Tips

- Use broad terms first, then narrow down (e.g., "search" before "search slack messages")
- The Agent tool can handle tasks that don't require a specific tool
"""

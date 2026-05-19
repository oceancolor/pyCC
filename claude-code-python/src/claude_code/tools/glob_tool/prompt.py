"""GlobTool prompt constants.

Ported from: tools/GlobTool/prompt.ts

Contains the tool name and description string used to register GlobTool
in the tool catalogue and displayed to the model.
"""
from __future__ import annotations

#: The API-level tool name used to identify the Glob tool.
GLOB_TOOL_NAME: str = "Glob"

#: Multi-line description shown in the tool catalogue.
DESCRIPTION: str = (
    '- Fast file pattern matching tool that works with any codebase size\n'
    '- Supports glob patterns like "**/*.js" or "src/**/*.ts"\n'
    "- Returns matching file paths sorted by modification time\n"
    "- Use this tool when you need to find files by name patterns\n"
    "- When you are doing an open ended search that may require multiple "
    "rounds of globbing and grepping, use the Agent tool instead"
)

__all__ = ["GLOB_TOOL_NAME", "DESCRIPTION"]

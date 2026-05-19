"""ConfigTool package.

Re-exports the ConfigTool class and its canonical name constant.

ConfigTool allows agents to read and write Claude Code configuration values
(model, permissions, hooks, etc.) through a structured API rather than
editing JSON files directly.

Ported from: tools/ConfigTool/ (TypeScript)

Usage::

    from claude_code.tools.config_tool import ConfigTool, CONFIG_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.config_tool.config_tool import ConfigTool
from claude_code.tools.config_tool.constants import CONFIG_TOOL_NAME

__all__ = [
    "ConfigTool",
    "CONFIG_TOOL_NAME",
]

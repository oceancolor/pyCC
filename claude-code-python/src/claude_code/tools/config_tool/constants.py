"""ConfigTool constants.

Ported from: tools/ConfigTool/constants.ts

Defines the canonical API-level tool name used to identify the Config tool
in tool-use messages and permission rules.

The Config tool allows agents to read and update Claude Code configuration
values without directly editing JSON files.  Keeping the name in a
separate constants module avoids circular imports between the tool class
and the settings modules that need the name string.

See also
--------
``claude_code.tools.config_tool.config_tool`` : The Config tool implementation.
``claude_code.constants.tools`` : Central tool-name registry.
"""
from __future__ import annotations

#: The API-level tool name used to identify the Config tool.
CONFIG_TOOL_NAME: str = "Config"

__all__ = ["CONFIG_TOOL_NAME"]

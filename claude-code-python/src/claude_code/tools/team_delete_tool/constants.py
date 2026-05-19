"""TeamDeleteTool constants.

Ported from: tools/TeamDeleteTool/constants.ts

Defines the canonical API-level tool name used to identify the
TeamDelete tool in tool-use messages and permission rules.

TeamDelete tears down a named team by removing the team directory and
associated task directory.  All teammate agents must be terminated before
calling this tool, otherwise it will return an error.

See also
--------
``claude_code.tools.team_delete_tool.team_delete_tool`` : Implementation.
``claude_code.tools.team_create_tool.constants`` : Related TeamCreate name.
"""
from __future__ import annotations

#: The API-level tool name used to identify the TeamDelete tool.
TEAM_DELETE_TOOL_NAME: str = "TeamDelete"

__all__ = ["TEAM_DELETE_TOOL_NAME"]

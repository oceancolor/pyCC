"""TeamCreateTool constants.

Ported from: tools/TeamCreateTool/constants.ts

Defines the canonical API-level tool name used to identify the
TeamCreate tool in tool-use messages and permission rules.

TeamCreate provisions a new named team directory structure so that the
root agent can spawn and coordinate teammate sub-agents.  It is the
entry-point for multi-agent swarm workflows.

See also
--------
``claude_code.tools.team_create_tool.team_create_tool`` : Implementation.
``claude_code.tools.team_delete_tool.constants`` : Related TeamDelete name.
"""
from __future__ import annotations

#: The API-level tool name used to identify the TeamCreate tool.
TEAM_CREATE_TOOL_NAME: str = "TeamCreate"

__all__ = ["TEAM_CREATE_TOOL_NAME"]

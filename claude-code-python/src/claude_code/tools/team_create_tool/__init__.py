"""TeamCreateTool package.

Re-exports TeamCreateTool and its canonical name constant.

TeamCreateTool provisions a new named team and its associated directory
structure (``~/.claude/teams/<name>/``) so that the root agent can spawn
and coordinate teammate sub-agents.

Ported from: tools/TeamCreateTool/ (TypeScript)

Usage::

    from claude_code.tools.team_create_tool import TeamCreateTool, TEAM_CREATE_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.team_create_tool.team_create_tool import TeamCreateTool
from claude_code.tools.team_create_tool.constants import TEAM_CREATE_TOOL_NAME

__all__ = [
    "TeamCreateTool",
    "TEAM_CREATE_TOOL_NAME",
]

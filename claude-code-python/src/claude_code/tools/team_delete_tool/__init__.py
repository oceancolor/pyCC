"""TeamDeleteTool package.

Re-exports TeamDeleteTool and its canonical name constant.

TeamDeleteTool tears down a named team by removing the team directory
(``~/.claude/teams/<name>/``) and the associated task directory.  All
teammate agents must be terminated before calling this tool.

Ported from: tools/TeamDeleteTool/ (TypeScript)

Usage::

    from claude_code.tools.team_delete_tool import TeamDeleteTool, TEAM_DELETE_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.team_delete_tool.team_delete_tool import TeamDeleteTool
from claude_code.tools.team_delete_tool.constants import TEAM_DELETE_TOOL_NAME

__all__ = [
    "TeamDeleteTool",
    "TEAM_DELETE_TOOL_NAME",
]

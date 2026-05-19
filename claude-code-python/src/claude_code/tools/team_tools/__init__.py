"""TeamTools package.

Re-exports both team management tools from their implementation modules
inside this directory.

TeamCreateTool and TeamDeleteTool manage the lifecycle of a named agent
swarm: creating the team directory structure and tearing it down once all
teammate agents have finished.

Ported from: tools/TeamCreateTool/ and tools/TeamDeleteTool/ (TypeScript)

Usage::

    from claude_code.tools.team_tools import TeamCreateTool, TeamDeleteTool
"""
from __future__ import annotations

from claude_code.tools.team_tools.team_create_tool import TeamCreateTool
from claude_code.tools.team_tools.team_delete_tool import TeamDeleteTool

__all__ = [
    "TeamCreateTool",
    "TeamDeleteTool",
]

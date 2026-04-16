"""TeamDelete tool stub. Ported from TeamDeleteTool."""
from __future__ import annotations
from typing import Any

TEAM_DELETE_TOOL_NAME = "TeamDelete"
DESCRIPTION = "Remove team and task directories when swarm work is complete"

PROMPT = """Remove team and task directories when the swarm work is complete.

**IMPORTANT**: TeamDelete will fail if the team still has active members. Gracefully terminate teammates first."""


class TeamDeleteTool:
    name = TEAM_DELETE_TOOL_NAME
    description = DESCRIPTION

    async def call(self, **kwargs: Any) -> dict:
        return {"error": "TeamDelete requires agent swarms — not available in this environment"}

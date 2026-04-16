"""Team delete tool stub. Ported from TeamDeleteTool."""
from __future__ import annotations
from typing import Any

TEAM_DELETE_TOOL_NAME = "TeamDelete"
DESCRIPTION = "Remove team and task directories when swarm work is complete"


class TeamDeleteTool:
    name = TEAM_DELETE_TOOL_NAME
    description = DESCRIPTION

    async def call(self, **kwargs: Any) -> dict:
        return {"error": "TeamDelete not available in this environment (requires agent swarms)"}

"""Team create tool stub. Ported from TeamCreateTool."""
from __future__ import annotations
from typing import Any

TEAM_CREATE_TOOL_NAME = "TeamCreate"
DESCRIPTION = "Create a new agent team for multi-agent coordination"


class TeamCreateTool:
    name = TEAM_CREATE_TOOL_NAME
    description = DESCRIPTION

    async def call(self, team_name: str, **kwargs: Any) -> dict:
        return {"error": "TeamCreate not available in this environment (requires agent swarms)"}

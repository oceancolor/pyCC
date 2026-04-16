"""TeamCreate tool stub. Ported from TeamCreateTool."""
from __future__ import annotations
from typing import Any, List, Optional

TEAM_CREATE_TOOL_NAME = "TeamCreate"
DESCRIPTION = "Create a new agent team for multi-agent coordination"

PROMPT = """Create a new swarm team and assign teammates to it.

This operation:
- Creates team directory (`~/.claude/teams/{team-name}/`)
- Creates task directory (`~/.claude/tasks/{team-name}/`)
- Sets up team context for the current session

Use this when starting a multi-agent task that benefits from parallel execution."""


class TeamCreateTool:
    name = TEAM_CREATE_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "team_name": {"type": "string", "description": "Name of the team"},
                    "teammates": {"type": "array", "items": {"type": "string"},
                                  "description": "List of teammate agent IDs or names"},
                },
                "required": ["team_name"]
            }
        }

    async def call(self, team_name: str = "", teammates: Optional[List[str]] = None, **kwargs: Any) -> dict:
        return {"error": "TeamCreate requires agent swarms — not available in this environment"}

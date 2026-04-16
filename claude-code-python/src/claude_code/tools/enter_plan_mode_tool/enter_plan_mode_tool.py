"""EnterPlanMode tool. Ported from EnterPlanModeTool."""
from __future__ import annotations

ENTER_PLAN_MODE_TOOL_NAME = "EnterPlanMode"
DESCRIPTION = "Enter plan mode to create a step-by-step plan before executing"

PLAN_MODE_DESCRIPTION = """
Switch from execution mode to plan mode. In plan mode:
- Claude outlines steps without executing them
- The user can review and approve before work begins
- Use when tasks are complex or irreversible
""".strip()


class EnterPlanModeTool:
    name = ENTER_PLAN_MODE_TOOL_NAME
    description = DESCRIPTION

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {"type": "object", "properties": {}, "required": []}
        }

    async def call(self, **kwargs) -> dict:
        return {"mode": "plan", "status": "entered plan mode"}

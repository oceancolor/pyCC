"""
ExitPlanModeTool — signal plan is complete and ready for user approval.
Ported from ExitPlanModeTool/ExitPlanModeV2Tool.ts (493 lines → core).
"""
from __future__ import annotations
from typing import Any

from claude_code.tools.exit_plan_mode_tool.constants import EXIT_PLAN_MODE_V2_TOOL_NAME


class ExitPlanModeTool:
    name = EXIT_PLAN_MODE_V2_TOOL_NAME
    description = (
        "Use when in plan mode and finished writing the plan file, "
        "ready for user approval."
    )
    is_read_only = True

    async def call(self, context: Any = None) -> dict:
        # In plan mode: read the plan file and return it for approval
        plan_path = getattr(context, "plan_file_path", None)
        if plan_path:
            import os
            if os.path.exists(plan_path):
                with open(plan_path, "r") as f:
                    plan_content = f.read()
                return {
                    "type": "plan_approval_requested",
                    "plan_file": plan_path,
                    "plan_content": plan_content,
                }
        return {"type": "plan_approval_requested", "plan_content": ""}

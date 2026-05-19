"""EnterPlanModeTool constants.

Ported from: tools/EnterPlanModeTool/constants.ts

Defines the canonical API-level tool name used to identify the
EnterPlanMode tool in tool-use messages and permission rules.

Plan mode is a two-phase workflow where the agent first proposes a plan
and waits for human confirmation before executing any changes.  The
``EnterPlanMode`` tool name is the trigger that switches the session into
this mode.

See also
--------
``claude_code.tools.exit_plan_mode_tool.constants`` : ExitPlanMode name.
``claude_code.tools.enter_plan_mode_tool.enter_plan_mode_tool`` : Implementation.
"""
from __future__ import annotations

#: The API-level tool name used to identify the EnterPlanMode tool.
ENTER_PLAN_MODE_TOOL_NAME: str = "EnterPlanMode"

__all__ = ["ENTER_PLAN_MODE_TOOL_NAME"]

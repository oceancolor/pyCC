"""EnterPlanModeTool package.

Re-exports EnterPlanModeTool and its canonical name constant.

EnterPlanModeTool switches the current session into "plan mode", where the
agent proposes an action plan and waits for human confirmation before
executing any changes.

Ported from: tools/EnterPlanModeTool/ (TypeScript)

Usage::

    from claude_code.tools.enter_plan_mode_tool import (
        EnterPlanModeTool,
        ENTER_PLAN_MODE_TOOL_NAME,
    )
"""
from __future__ import annotations

from claude_code.tools.enter_plan_mode_tool.enter_plan_mode_tool import EnterPlanModeTool
from claude_code.tools.enter_plan_mode_tool.constants import ENTER_PLAN_MODE_TOOL_NAME

__all__ = [
    "EnterPlanModeTool",
    "ENTER_PLAN_MODE_TOOL_NAME",
]

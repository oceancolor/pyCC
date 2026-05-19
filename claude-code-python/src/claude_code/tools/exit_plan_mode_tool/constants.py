"""ExitPlanModeTool constants.

Ported from: tools/ExitPlanModeTool/constants.ts

Defines the canonical API-level tool names used to identify the
ExitPlanMode tool.  Both v1 and v2 share the same wire name.
"""
from __future__ import annotations

#: The API-level tool name for ExitPlanMode (v1).
EXIT_PLAN_MODE_TOOL_NAME: str = "ExitPlanMode"

#: The API-level tool name for ExitPlanMode v2.
#: Kept as a separate constant for forward-compatibility even though
#: it currently resolves to the same string as EXIT_PLAN_MODE_TOOL_NAME.
EXIT_PLAN_MODE_V2_TOOL_NAME: str = "ExitPlanMode"

__all__ = [
    "EXIT_PLAN_MODE_TOOL_NAME",
    "EXIT_PLAN_MODE_V2_TOOL_NAME",
]

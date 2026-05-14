"""EnterPlanModeTool prompt. Ported from EnterPlanModeTool/prompt.ts"""
from __future__ import annotations

ASK_USER_QUESTION_TOOL_NAME = "AskUserQuestion"

WHAT_HAPPENS_SECTION = f"""## What Happens in Plan Mode

In plan mode, you'll:
1. Thoroughly explore the codebase using Glob, Grep, and Read tools
2. Understand existing patterns and architecture
3. Design an implementation approach
4. Present your plan to the user for approval
5. Use {ASK_USER_QUESTION_TOOL_NAME} if you need to clarify approaches
6. Exit plan mode with ExitPlanMode when ready to implement

"""


def get_enter_plan_mode_tool_prompt() -> str:
    return f"""Use this tool to enter plan mode, where you'll explore and design a solution before implementing.

{WHAT_HAPPENS_SECTION}
## When to Use

- For complex tasks that benefit from upfront planning
- When the implementation approach is unclear
- When the user wants to review the plan before any changes are made

## Important

- In plan mode, do NOT make any file changes
- Use Read, Glob, Grep tools to explore
- Present your complete plan before calling ExitPlanMode
- If you have questions, use {ASK_USER_QUESTION_TOOL_NAME}
"""

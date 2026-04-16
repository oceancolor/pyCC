# Source: tools/ExitPlanModeTool/ExitPlanModeV2Tool.ts
"""ExitPlanMode tool: present plan for approval and transition out of plan mode."""
from __future__ import annotations

from typing import Any, Optional

from claude_code.tool import Tool, ToolInputJSONSchema, ToolUseContext
from claude_code.utils.plans import get_plan, get_plan_file_path

EXIT_PLAN_MODE_V2_TOOL_NAME = "ExitPlanMode"


class ExitPlanModeV2Tool(Tool):
    """Tool for exiting plan mode after writing a plan."""

    name = EXIT_PLAN_MODE_V2_TOOL_NAME
    search_hint = "present plan for approval and start coding (plan mode only)"

    async def description(self) -> str:
        return "Prompts the user to exit plan mode and start coding."

    async def prompt(self) -> str:
        return (
            "Use this tool when you have finished writing your plan and are ready "
            "to present it to the user for approval. This will exit plan mode and "
            "allow you to begin implementing the plan."
        )

    def input_schema(self) -> ToolInputJSONSchema:
        return {
            "type": "object",
            "properties": {
                "allowedPrompts": {
                    "type": "array",
                    "description": (
                        "Prompt-based permissions needed to implement the plan. "
                        "Describes categories of actions rather than specific commands."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "tool": {
                                "type": "string",
                                "enum": ["Bash"],
                                "description": "The tool this prompt applies to",
                            },
                            "prompt": {
                                "type": "string",
                                "description": (
                                    "Semantic description, e.g. 'run tests', 'install dependencies'"
                                ),
                            },
                        },
                        "required": ["tool", "prompt"],
                    },
                },
            },
        }

    async def call(self, input_data: dict[str, Any], context: ToolUseContext) -> Any:
        """Exit plan mode: read plan from disk and present to user."""
        agent_id: Optional[str] = getattr(context, "agent_id", None)

        # CCR web UI may send an edited plan via input
        input_plan: Optional[str] = input_data.get("plan") if isinstance(input_data.get("plan"), str) else None
        plan = input_plan or get_plan(agent_id=agent_id)
        file_path = get_plan_file_path(agent_id=agent_id)
        is_agent = agent_id is not None

        # Save edited plan to disk if provided
        if input_plan is not None and file_path:
            import asyncio
            loop = asyncio.get_event_loop()
            import os
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(input_plan)

        if not plan or plan.strip() == "":
            return {
                "plan": None,
                "is_agent": is_agent,
                "file_path": file_path,
                "tool_result": "User has approved exiting plan mode. You can now proceed.",
            }

        result_text = (
            f"User has approved your plan. You can now start coding. "
            f"Start with updating your todo list if applicable.\n\n"
            f"Your plan has been saved to: {file_path}\n\n"
            f"## Approved Plan:\n{plan}"
        )

        return {
            "plan": plan,
            "is_agent": is_agent,
            "file_path": file_path,
            "plan_was_edited": input_plan is not None,
            "tool_result": result_text,
        }

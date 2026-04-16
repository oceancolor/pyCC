"""TaskOutputTool — retrieve a task's output file. Ported from tools."""
from __future__ import annotations
import os
from typing import Any, Dict

TASK_OUTPUT_TOOL_NAME = "TaskOutput"

class TaskOutputTool:
    name = TASK_OUTPUT_TOOL_NAME
    description = "Get the output of a completed background task."
    is_read_only = True

    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        }

    async def call(self, input: Dict[str, Any], context: Any = None) -> dict:
        task_id = input.get("task_id", "")
        output_dir = os.path.join(os.path.expanduser("~"), ".claude", "agent-outputs")
        output_file = os.path.join(output_dir, f"{task_id}.txt")
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                content = f.read()
            return {"text": content}
        return {"text": f"No output found for task {task_id}"}

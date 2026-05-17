"""TaskOutputTool — retrieve output from a background task. Ported from TaskOutputTool/."""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, Optional

TASK_OUTPUT_TOOL_NAME = "TaskOutput"
# Backward-compatible aliases (TS uses ``aliases: ['AgentOutputTool', 'BashOutputTool']``)
TASK_OUTPUT_TOOL_ALIASES = ["AgentOutputTool", "BashOutputTool"]

PROMPT = """DEPRECATED: Prefer using the Read tool on the task's output file path instead.
Background tasks return their output file path in the tool result, and you receive a
<task-notification> with the same path when the task completes — Read that file directly.

- Retrieves output from a running or completed task (background shell, agent, or remote session)
- Takes a task_id parameter identifying the task
- Returns the task output along with status information
- Use block=true (default) to wait for task completion
- Use block=false for non-blocking check of current status
- Task IDs can be found using the /tasks command
- Works with all task types: background shells, async agents, and remote sessions"""


class TaskOutputTool:
    """Read the output of a background task (deprecated — prefer file Read).

    Mirrors the TS TaskOutputTool:
    - Supports blocking (wait for completion) and non-blocking modes.
    - Falls back to reading a text file under ~/.claude/agent-outputs/ when the
      in-memory task state is unavailable.
    """

    name = TASK_OUTPUT_TOOL_NAME
    description = "[Deprecated] — prefer Read on the task output file path"
    aliases = TASK_OUTPUT_TOOL_ALIASES
    should_defer = True
    is_read_only = True
    is_concurrency_safe = True

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": {
                    "task_id": {
                        "type": "string",
                        "description": "The task ID to get output from",
                    },
                    "block": {
                        "type": "boolean",
                        "description": "Whether to wait for completion (default: true)",
                        "default": True,
                    },
                    "timeout": {
                        "type": "number",
                        "description": "Max wait time in ms (default: 30000)",
                        "default": 30000,
                        "minimum": 0,
                        "maximum": 600000,
                    },
                },
                "required": ["task_id"],
            },
        }

    async def call(
        self,
        task_id: str,
        block: bool = True,
        timeout: int = 30000,
        context: Any = None,
        **kwargs: Any,
    ) -> dict:
        output = await self._get_task_output(task_id, block, timeout)
        return output

    async def _get_task_output(
        self,
        task_id: str,
        block: bool,
        timeout_ms: int,
    ) -> dict:
        """Try in-memory task registry first, fall back to disk."""
        # Attempt in-memory task lookup
        try:
            from claude_code.services.task_manager import get_task_manager

            tm = get_task_manager()
            task = tm.get_task(task_id)
        except Exception:
            task = None

        if task is None:
            # No in-memory record — read from disk (legacy path)
            output = self._read_disk_output(task_id)
            return {
                "retrieval_status": "success" if output else "not_ready",
                "task": {
                    "task_id": task_id,
                    "task_type": "unknown",
                    "status": "unknown",
                    "description": "",
                    "output": output or "",
                }
                if output
                else None,
            }

        status = task.get("status", "pending")

        if not block or status not in ("running", "pending"):
            output = self._read_disk_output(task_id) or task.get("output", "")
            return {
                "retrieval_status": "success" if status not in ("running", "pending") else "not_ready",
                "task": {
                    "task_id": task_id,
                    "task_type": task.get("type", "local_bash"),
                    "status": status,
                    "description": task.get("description", ""),
                    "output": output,
                    "error": task.get("error"),
                },
            }

        # Blocking wait
        timeout_secs = timeout_ms / 1000.0
        elapsed = 0.0
        poll_interval = 0.1

        while elapsed < timeout_secs:
            await asyncio.sleep(poll_interval)
            elapsed += poll_interval
            task = tm.get_task(task_id)
            if task is None:
                break
            status = task.get("status", "pending")
            if status not in ("running", "pending"):
                break

        if task is None:
            return {"retrieval_status": "timeout", "task": None}

        status = task.get("status", "pending")
        if status in ("running", "pending"):
            # Still running after timeout
            output = self._read_disk_output(task_id) or task.get("output", "")
            return {
                "retrieval_status": "timeout",
                "task": {
                    "task_id": task_id,
                    "task_type": task.get("type", "local_bash"),
                    "status": status,
                    "description": task.get("description", ""),
                    "output": output,
                },
            }

        output = self._read_disk_output(task_id) or task.get("output", "")
        return {
            "retrieval_status": "success",
            "task": {
                "task_id": task_id,
                "task_type": task.get("type", "local_bash"),
                "status": status,
                "description": task.get("description", ""),
                "output": output,
                "error": task.get("error"),
            },
        }

    @staticmethod
    def _read_disk_output(task_id: str) -> Optional[str]:
        output_dir = os.path.join(os.path.expanduser("~"), ".claude", "agent-outputs")
        output_file = os.path.join(output_dir, f"{task_id}.txt")
        if os.path.exists(output_file):
            with open(output_file) as fh:
                return fh.read()
        return None

    def map_tool_result(self, content: dict, tool_use_id: str) -> dict:
        parts = [f"<retrieval_status>{content.get('retrieval_status', '')}</retrieval_status>"]
        task = content.get("task")
        if task:
            parts.append(f"<task_id>{task.get('task_id', '')}</task_id>")
            parts.append(f"<task_type>{task.get('task_type', '')}</task_type>")
            parts.append(f"<status>{task.get('status', '')}</status>")
            if task.get("output", "").strip():
                parts.append(f"<output>\n{task['output'].rstrip()}\n</output>")
            if task.get("error"):
                parts.append(f"<error>{task['error']}</error>")

        return {
            "tool_use_id": tool_use_id,
            "type": "tool_result",
            "content": "\n\n".join(parts),
        }

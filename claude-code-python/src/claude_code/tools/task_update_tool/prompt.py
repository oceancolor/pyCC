"""TaskUpdateTool prompt. Ported from TaskUpdateTool/prompt.ts"""
from __future__ import annotations

DESCRIPTION = "Update a task in the task list"

PROMPT = """Use this tool to update a task in the task list.

## When to Use This Tool

**Mark tasks as resolved:**
- When you have completed the work described in a task
- When a task is no longer needed or has been superseded
- IMPORTANT: Always mark your assigned tasks as resolved when you finish them
- After resolving, call TaskList to find your next task

- ONLY mark a task as completed when you have FULLY accomplished it
- If you encounter errors, blockers, or cannot finish, keep the task as in_progress
- When blocked, create a new task describing what needs to be resolved
- Never mark a task as completed if:
  - Tests are failing
  - Implementation is partial
  - You encountered unresolved errors
  - You couldn't find necessary files or dependencies

**Set task status:**
- Set to 'in_progress' when you begin working on a task
- Set to 'completed' only when fully done

**Assign ownership:**
- Use the `owner` parameter to claim a task (set to your agent ID)
- Or assign a task to a specific teammate

**Manage dependencies:**
- Use `blocks` to indicate which tasks depend on this one
- Use `blockedBy` to indicate what this task is waiting on
"""

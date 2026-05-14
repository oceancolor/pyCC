"""TodoWriteTool prompt. Ported from TodoWriteTool/prompt.ts"""
from __future__ import annotations

PROMPT = """Use this tool to create and manage a structured task list for your current coding session. This helps you track progress, organize complex tasks, and demonstrate thoroughness to the user.
It also helps the user understand the progress of the task and overall progress of their requests.

## When to Use This Tool
Use this tool proactively in these scenarios:

1. Complex multi-step tasks - When a task requires 3 or more distinct steps or actions
2. Non-trivial and complex tasks - Tasks that require careful planning or multiple operations
3. User explicitly requests todo list - When the user directly asks you to use the todo list
4. User provides multiple tasks - When users provide a list of things to be done (numbered or comma-separated)
5. After receiving new instructions - Immediately capture user requirements as todos
6. When you start working on a task - Mark it as in_progress BEFORE beginning work. Ideally you should only have one todo as in_progress at a time
7. After completing a task - Mark it as completed and add any new follow-up tasks discovered during implementation

## When NOT to Use This Tool

Skip using this tool when:
1. There is only a single, straightforward task
2. The task is trivial and can be completed in one or two steps
3. The task is purely conversational or informational

## Todo Item States

- **pending**: Task not yet started
- **in_progress**: Task currently being worked on (keep to one at a time)
- **completed**: Task fully finished

## Tips

- Keep subjects brief and actionable
- Always update status as you work — don't batch updates
- When you finish a task, immediately check what's next
- Use Edit tool for file edits, not for managing todos
"""

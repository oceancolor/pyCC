"""EnterWorktreeTool prompt. Ported from EnterWorktreeTool/prompt.ts"""
from __future__ import annotations


def get_enter_worktree_tool_prompt() -> str:
    return """Use this tool ONLY when the user explicitly asks to work in a worktree. This tool creates an isolated git worktree and switches the current session into it.

## When to Use

- The user explicitly says "worktree" (e.g., "start a worktree", "work in a worktree", "create a worktree", "use a worktree")

## When NOT to Use

- The user asks to create a branch, switch branches, or work on a different branch — use git commands instead
- The user asks to fix a bug or work on a feature — use normal git workflow unless they specifically mention worktrees
- Never use this tool unless the user explicitly mentions "worktree"

## Requirements

- Must be in a git repository, OR have WorktreeCreate/WorktreeRemove hooks configured in settings.json
- Must not already be in a worktree

## Behavior

Creates a new git worktree in a temp directory, switches the session context to that directory, and returns the new path. Use ExitWorktree when done to return to the original directory.
"""

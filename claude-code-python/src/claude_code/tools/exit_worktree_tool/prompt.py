"""ExitWorktreeTool prompt. Ported from ExitWorktreeTool/prompt.ts"""
from __future__ import annotations


def get_exit_worktree_tool_prompt() -> str:
    return """Exit a worktree session created by EnterWorktree and return the session to the original working directory.

## Scope

This tool ONLY operates on worktrees created by EnterWorktree in this session. It will NOT touch:
- Worktrees you created manually with `git worktree add`
- Worktrees from a previous session (even if created by EnterWorktree then)
- The directory you're in if EnterWorktree was never called

If called outside an EnterWorktree session, the tool is a **no-op**: it reports that no worktree session is active and takes no action. Filesystem state is unchanged.

## When to Use

- The user explicitly asks to "exit the worktree", "leave the worktree", "go back", or otherwise end the worktree session
- Do NOT call this proactively — only when the user asks

## Parameters

- `action` (required): `"keep"` or `"remove"`
  - `"keep"`: exit and leave the worktree directory in place (useful if you want to reference it later)
  - `"remove"`: exit and delete the worktree directory (clean up)
"""

"""
/commit command. Ported from commands/commit.ts
"""
from __future__ import annotations
from claude_code.commands import Command

ALLOWED_TOOLS = [
    "Bash(git add:*)",
    "Bash(git status:*)",
    "Bash(git commit:*)",
]

COMMIT_PROMPT = """## Context
- Current git status: !`git status`
- Current git diff (staged and unstaged changes): !`git diff HEAD`
- Current branch: !`git branch --show-current`
- Recent commits: !`git log --oneline -10`

## Git Safety Protocol
- NEVER update the git config
- NEVER skip hooks (--no-verify) unless user explicitly requests it
- CRITICAL: ALWAYS create NEW commits. NEVER use git commit --amend unless user explicitly requests
- Do not commit files containing secrets (.env, credentials.json, etc)
- If no changes to commit, do not create an empty commit

## Your task
Create a single git commit based on the above changes:
1. Analyze staged changes and draft a commit message
2. Stage relevant files and create the commit using HEREDOC syntax
"""


class CommitCommand(Command):
    type = "prompt"
    name = "commit"
    description = "Create a git commit"
    allowed_tools = ALLOWED_TOOLS
    progress_message = "creating commit"
    source = "builtin"

    async def get_prompt_for_command(self, args: str, context=None) -> list:
        return [{"type": "text", "text": COMMIT_PROMPT}]


commit = CommitCommand()

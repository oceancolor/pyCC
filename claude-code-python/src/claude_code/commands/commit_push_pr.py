"""
/commit-push-pr command. Ported from commands/commit-push-pr.ts
"""
from __future__ import annotations
from claude_code.commands import Command

ALLOWED_TOOLS = [
    "Bash(git checkout --branch:*)", "Bash(git checkout -b:*)",
    "Bash(git add:*)", "Bash(git status:*)", "Bash(git push:*)",
    "Bash(git commit:*)", "Bash(gh pr create:*)", "Bash(gh pr edit:*)",
    "Bash(gh pr view:*)", "Bash(gh pr merge:*)", "ToolSearch",
]

COMMIT_PUSH_PR_PROMPT = """Commit all changes, push to remote, and create/update a pull request.

Steps:
1. Check git status and stage appropriate files
2. Create a descriptive commit (or amend if appropriate)
3. Push the branch to remote
4. Create or update a PR with gh pr create / gh pr edit
5. Output the PR URL

Git Safety Protocol:
- NEVER skip hooks (--no-verify) unless user explicitly requests
- Do not commit secrets or credentials
"""


class CommitPushPrCommand(Command):
    type = "prompt"
    name = "commit-push-pr"
    description = "Commit, push, and open a PR"
    allowed_tools = ALLOWED_TOOLS
    progress_message = "creating PR"
    source = "builtin"

    async def get_prompt_for_command(self, args: str, context=None) -> list:
        return [{"type": "text", "text": COMMIT_PUSH_PR_PROMPT}]


commit_push_pr = CommitPushPrCommand()

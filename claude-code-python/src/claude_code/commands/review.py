"""
/review and /ultrareview commands. Ported from commands/review.ts
"""
from __future__ import annotations
from claude_code.commands import Command

LOCAL_REVIEW_PROMPT = """You are an expert code reviewer. Follow these steps:
1. If no PR number is provided in the args, run `gh pr list` to show open PRs
2. If a PR number is provided, run `gh pr view <number>` to get PR details
3. Run `gh pr diff <number>` to get the diff
4. Analyze the changes and provide a thorough code review that includes:
   - Overview of what the PR does
   - Code quality and style analysis
   - Specific improvement suggestions
   - Potential issues or risks

PR number: {args}"""


class ReviewCommand(Command):
    type = "prompt"
    name = "review"
    description = "Review a pull request"
    progress_message = "reviewing pull request"
    source = "builtin"

    async def get_prompt_for_command(self, args: str, context=None) -> list:
        return [{"type": "text", "text": LOCAL_REVIEW_PROMPT.format(args=args)}]


class UltrareviewCommand(Command):
    type = "local"
    name = "ultrareview"
    description = "~10–20 min · Finds and verifies bugs in your branch (requires subscription)"
    source = "builtin"

    def is_enabled(self) -> bool:
        return False  # Requires claude.ai OAuth

    async def call(self, args: str, context=None) -> dict:
        return {"type": "text", "value": "Ultrareview requires a Claude.ai subscription."}


review = ReviewCommand()
ultrareview = UltrareviewCommand()

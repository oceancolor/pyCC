"""
/security-review command (moved to plugin). Ported from commands/security-review.ts
"""
from __future__ import annotations
from claude_code.commands.create_moved_to_plugin_command import create_moved_to_plugin_command

SECURITY_REVIEW_PROMPT = """You are a senior security engineer conducting a focused security review.

GIT STATUS: !`git status`
FILES MODIFIED: !`git diff --name-only origin/HEAD...`
DIFF CONTENT: !`git diff origin/HEAD...`

Perform a security-focused review:
- Only flag issues with >80% confidence of actual exploitability
- Focus on unauthorized access, data breaches, system compromise
- Skip: DoS, secrets on disk, rate limiting, theoretical issues
"""


async def _fallback_prompt(args: str, context=None) -> list:
    return [{"type": "text", "text": SECURITY_REVIEW_PROMPT}]


security_review = create_moved_to_plugin_command(
    name="security-review",
    description="Complete a security review of the pending changes on the current branch",
    progress_message="running security review",
    plugin_name="security-review",
    plugin_command="review",
    get_prompt_while_marketplace_private=_fallback_prompt,
)

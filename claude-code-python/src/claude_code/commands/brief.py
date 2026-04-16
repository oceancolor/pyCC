"""
/brief command. Ported from commands/brief.ts
"""
from __future__ import annotations
from claude_code.commands import Command

BRIEF_PROMPT = """Create a brief description of what you are currently working on.
Summarize:
1. The current task or feature being implemented
2. What has been completed so far
3. What remains to be done
4. Any blockers or open questions

Keep it concise (3-5 sentences max)."""


class BriefCommand(Command):
    type = "prompt"
    name = "brief"
    description = "Get a brief summary of the current task"
    progress_message = "creating brief"
    source = "builtin"

    async def get_prompt_for_command(self, args: str, context=None) -> list:
        return [{"type": "text", "text": BRIEF_PROMPT}]


brief = BriefCommand()

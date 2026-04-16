"""
/init command. Ported from commands/init.ts
"""
from __future__ import annotations
from claude_code.commands import Command

INIT_PROMPT = """Set up a minimal CLAUDE.md (and optionally skills and hooks) for this repo.
CLAUDE.md is loaded into every Claude Code session, so it must be concise — only include what Claude would get wrong without it.

Phase 1: Ask what to set up
- Which CLAUDE.md files: Project | Personal (gitignored) | Both
- Also set up skills and hooks? Yes/No

Phase 2: Explore the codebase
Survey key files: manifest files, README, Makefile, CI config, existing CLAUDE.md.
Detect build/test/lint commands, languages, frameworks.

Phase 3: Write the CLAUDE.md
Keep it concise. Include:
1. Build/test/lint commands (especially non-standard ones)
2. High-level architecture (what requires reading multiple files to understand)
3. Key conventions and gotchas

Do NOT include obvious instructions or generic dev practices.
"""


class InitCommand(Command):
    type = "prompt"
    name = "init"
    description = "Initialize a CLAUDE.md file for this project"
    progress_message = "initializing project"
    source = "builtin"

    async def get_prompt_for_command(self, args: str, context=None) -> list:
        return [{"type": "text", "text": INIT_PROMPT}]


init_cmd = InitCommand()

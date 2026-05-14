"""SkillTool prompt. Ported from SkillTool/prompt.ts"""
from __future__ import annotations

DESCRIPTION = "Execute a named skill (slash command) with an optional prompt"

PROMPT = """Execute a named skill or slash command.

Skills are reusable workflows defined in .claude/skills/ or installed globally.
They can be simple prompt templates or complex multi-step workflows.

## When to Use

- When the user invokes a slash command (e.g., /review, /test, /deploy)
- When running a named workflow that has been defined as a skill
- When you want to invoke a pre-defined sequence of operations

## Usage

Provide the skill name and any required parameters. The skill will be loaded and executed with the provided context.

## Tips

- Skills can chain multiple tools together
- Custom skills can be defined in .claude/skills/<name>.md
- Use ToolSearch to discover available skills
"""

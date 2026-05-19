"""SkillTool package.

Re-exports SkillTool and its canonical name constant.

SkillTool reads and executes Claude Code skills — structured instruction
files (``SKILL.md``) that extend the agent's behaviour for specific
domains without requiring code changes.

Ported from: tools/SkillTool/ (TypeScript)

Usage::

    from claude_code.tools.skill_tool import SkillTool, SKILL_TOOL_NAME
"""
from __future__ import annotations

from claude_code.tools.skill_tool.skill_tool import SkillTool
from claude_code.tools.skill_tool.constants import SKILL_TOOL_NAME

__all__ = [
    "SkillTool",
    "SKILL_TOOL_NAME",
]

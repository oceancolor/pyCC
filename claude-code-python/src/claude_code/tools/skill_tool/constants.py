"""SkillTool constants.

Ported from: tools/SkillTool/constants.ts

Defines the canonical API-level tool name used to identify the Skill tool
in tool-use messages and permission rules.

The Skill tool reads ``SKILL.md`` files from the skills directory and
executes the instructions they contain.  Keeping the name in its own
constants module prevents circular imports between the skill loader and
the main tool registry.

See also
--------
``claude_code.tools.skill_tool.skill_tool`` : The Skill tool implementation.
``claude_code.utils.skills`` : Skills discovery and caching utilities.
"""
from __future__ import annotations

#: The API-level tool name used to identify the Skill tool.
SKILL_TOOL_NAME: str = "Skill"

__all__ = ["SKILL_TOOL_NAME"]

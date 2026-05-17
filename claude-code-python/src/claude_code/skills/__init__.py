"""
Skills package.
Ported from: src/skills/ (TypeScript)

Provides the user-defined skill/tool-set system for Claude Code:
  - SkillDefinition — parsed skill metadata (from YAML / JSON files)
  - Skill           — a loaded, possibly-enabled skill instance
  - SkillRegistry   — loads, registers, and retrieves skills
"""
from __future__ import annotations

from .types import (
    Skill,
    SkillDefinition,
)
from .registry import (
    SkillRegistry,
    get_skill_registry,
)

__all__ = [
    "Skill",
    "SkillDefinition",
    "SkillRegistry",
    "get_skill_registry",
]

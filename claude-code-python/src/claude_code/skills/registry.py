# 原始 TS: skills/registry.ts
"""技能注册表：加载/管理 skills"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional
from .types import Skill, SkillDefinition

_SKILLS_DIR = Path.home() / ".claude" / "skills"


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: Dict[str, Skill] = {}

    def register(self, skill: Skill) -> None:
        self._skills[skill.name] = skill

    def unregister(self, name: str) -> None:
        self._skills.pop(name, None)

    def get(self, name: str) -> Optional[Skill]:
        return self._skills.get(name)

    def all_skills(self) -> List[Skill]:
        return [s for s in self._skills.values() if s.enabled]

    def load_from_dir(self, skills_dir: Optional[Path] = None) -> int:
        """从目录加载技能定义文件（.json / .yaml）"""
        d = skills_dir or _SKILLS_DIR
        if not d.exists():
            return 0
        loaded = 0
        for f in d.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                defn = SkillDefinition(**{k: v for k, v in data.items()
                                          if k in SkillDefinition.__dataclass_fields__})
                self.register(Skill(definition=defn, source_path=str(f)))
                loaded += 1
            except (json.JSONDecodeError, TypeError):
                pass
        return loaded


_default_registry = SkillRegistry()

def get_skill_registry() -> SkillRegistry:
    return _default_registry

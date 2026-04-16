# 原始 TS: skills/types.ts
"""Skills 类型定义"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class SkillDefinition:
    """技能定义（YAML/JSON 格式的技能描述）"""
    name: str
    description: str
    version: str = "1.0.0"
    author: Optional[str] = None
    tools: List[str] = field(default_factory=list)  # 允许使用的工具名
    system_prompt: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Skill:
    """已加载的技能实例"""
    definition: SkillDefinition
    enabled: bool = True
    source_path: Optional[str] = None

    @property
    def name(self) -> str:
        return self.definition.name

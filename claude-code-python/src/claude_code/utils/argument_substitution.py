# 原始 TS: utils/argumentSubstitution.ts
"""命令参数替换（$VARIABLE、{placeholder} 等模板展开）"""
import os
import re
from typing import Dict, Optional


def substitute_env_vars(text: str) -> str:
    """替换 $VAR 和 ${VAR} 形式的环境变量"""
    def _replace(m: re.Match) -> str:
        name = m.group(1) or m.group(2)
        return os.environ.get(name, m.group(0))
    return re.sub(r'\$\{(\w+)\}|\$(\w+)', _replace, text)


def substitute_placeholders(text: str, vars: Dict[str, str]) -> str:
    """替换 {key} 形式的占位符"""
    for key, value in vars.items():
        text = text.replace(f"{{{key}}}", value)
    return text


def substitute_all(text: str, extra: Optional[Dict[str, str]] = None) -> str:
    """先替换 extra 占位符，再展开环境变量"""
    if extra:
        text = substitute_placeholders(text, extra)
    return substitute_env_vars(text)

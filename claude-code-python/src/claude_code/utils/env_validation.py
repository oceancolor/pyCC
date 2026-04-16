# 原始 TS: utils/envValidation.ts
"""环境变量校验"""
from __future__ import annotations
import os
from typing import List, Tuple


def validate_environment() -> Tuple[bool, List[str]]:
    """
    校验运行环境，返回 (ok, error_list)。
    """
    errors: List[str] = []

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        errors.append("ANTHROPIC_API_KEY 未设置")
    elif not (api_key.startswith("sk-ant-") or api_key.startswith("sk-")):
        errors.append("ANTHROPIC_API_KEY 格式不正确（应以 sk-ant- 或 sk- 开头）")

    return len(errors) == 0, errors


def assert_valid_environment() -> None:
    ok, errors = validate_environment()
    if not ok:
        raise EnvironmentError("\n".join(errors))

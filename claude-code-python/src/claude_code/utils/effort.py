# 原始 TS: utils/effort.ts
"""思考模式 (thinking/effort) 控制"""
from __future__ import annotations
import os
from typing import Literal, Optional

EffortLevel = Literal["low", "medium", "high", "auto"]


def get_default_effort() -> EffortLevel:
    raw = os.environ.get("CLAUDE_EFFORT", "auto").lower()
    if raw in ("low", "medium", "high", "auto"):
        return raw  # type: ignore
    return "auto"


def effort_to_budget_tokens(effort: EffortLevel) -> Optional[int]:
    """将 effort 等级转为 thinking budget_tokens"""
    mapping = {"low": 1024, "medium": 8192, "high": 32768, "auto": None}
    return mapping.get(effort)


def should_use_thinking(model: str, effort: EffortLevel = "auto") -> bool:
    thinking_models = {"claude-opus-4-5", "claude-opus-4", "claude-sonnet-4-5", "claude-sonnet-4"}
    return model in thinking_models and effort != "low"


def build_thinking_config(effort: EffortLevel, model: str) -> Optional[dict]:
    if not should_use_thinking(model, effort):
        return None
    budget = effort_to_budget_tokens(effort)
    if budget is None:
        return None
    return {"type": "enabled", "budget_tokens": budget}

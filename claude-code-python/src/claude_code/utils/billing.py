# 原始 TS: utils/billing.ts
"""计费信息工具（使用量统计与预算检查）"""
from dataclasses import dataclass, field
from typing import Dict, Optional


@dataclass
class UsageSummary:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str = "claude-opus-4-5"

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def add(self, other: "UsageSummary") -> None:
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_write_tokens += other.cache_write_tokens


# 简化定价表（USD per 1M tokens）
_PRICING: Dict[str, Dict[str, float]] = {
    "claude-opus-4-5":      {"input": 15.0,  "output": 75.0},
    "claude-sonnet-4-5":    {"input": 3.0,   "output": 15.0},
    "claude-haiku-3-5":     {"input": 0.8,   "output": 4.0},
    "claude-opus-4":        {"input": 15.0,  "output": 75.0},
    "claude-sonnet-4":      {"input": 3.0,   "output": 15.0},
}


def estimate_cost_usd(usage: UsageSummary) -> float:
    pricing = _PRICING.get(usage.model, {"input": 3.0, "output": 15.0})
    return (
        usage.input_tokens * pricing["input"] / 1_000_000
        + usage.output_tokens * pricing["output"] / 1_000_000
    )


def format_usage(usage: UsageSummary) -> str:
    cost = estimate_cost_usd(usage)
    return (
        f"in={usage.input_tokens:,} out={usage.output_tokens:,} "
        f"total={usage.total_tokens:,} ~${cost:.4f}"
    )

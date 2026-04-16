# 原始 TS: commands/status/
"""显示当前 session 状态：消息数、token 用量、模型、运行时间"""
import time
from dataclasses import dataclass, field
from typing import Optional


# Anthropic 定价（美元 / 1M tokens），截至 2024 年
_PRICING: dict = {
    "claude-3-5-sonnet-20241022": {"input": 3.0, "output": 15.0},
    "claude-3-5-haiku-20241022":  {"input": 0.8, "output": 4.0},
    "claude-3-opus-20240229":     {"input": 15.0, "output": 75.0},
    "claude-3-sonnet-20240229":   {"input": 3.0, "output": 15.0},
    "claude-3-haiku-20240307":    {"input": 0.25, "output": 1.25},
    # 默认兜底
    "__default__":                {"input": 3.0, "output": 15.0},
}


def _estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """根据模型和 token 数量估算费用（USD）"""
    pricing = _PRICING.get(model, _PRICING["__default__"])
    cost = (input_tokens / 1_000_000) * pricing["input"] + \
           (output_tokens / 1_000_000) * pricing["output"]
    return round(cost, 6)


@dataclass
class SessionStatus:
    message_count: int
    input_tokens: int
    output_tokens: int
    model: str
    start_time: float          # Unix timestamp (float)
    cost_usd: float

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time

    @property
    def elapsed_str(self) -> str:
        secs = int(self.elapsed_seconds)
        h, rem = divmod(secs, 3600)
        m, s = divmod(rem, 60)
        if h:
            return f"{h}h {m}m {s}s"
        if m:
            return f"{m}m {s}s"
        return f"{s}s"


def status_command(session_data: dict) -> SessionStatus:
    """
    从 session_data 字典构造 SessionStatus。

    期望的 session_data 结构（所有字段均为可选，缺失时用默认值）：
    {
        "message_count": int,
        "input_tokens":  int,
        "output_tokens": int,
        "model":         str,
        "start_time":    float,   # Unix timestamp
    }
    """
    model = session_data.get("model", "claude-3-5-sonnet-20241022")
    input_tokens = int(session_data.get("input_tokens", 0))
    output_tokens = int(session_data.get("output_tokens", 0))
    cost = _estimate_cost(model, input_tokens, output_tokens)

    return SessionStatus(
        message_count=int(session_data.get("message_count", 0)),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        model=model,
        start_time=float(session_data.get("start_time", time.time())),
        cost_usd=cost,
    )


def format_status(status: SessionStatus) -> str:
    """将 SessionStatus 格式化为人类可读的字符串"""
    lines = [
        "╔══════════════════════════════════════╗",
        "║         Claude Code - Session Status  ║",
        "╠══════════════════════════════════════╣",
        f"║  Model        : {status.model:<22}║",
        f"║  Messages     : {status.message_count:<22}║",
        f"║  Input tokens : {status.input_tokens:<22,}║",
        f"║  Output tokens: {status.output_tokens:<22,}║",
        f"║  Total tokens : {status.total_tokens:<22,}║",
        f"║  Cost (est.)  : ${status.cost_usd:<21.6f}║",
        f"║  Elapsed      : {status.elapsed_str:<22}║",
        "╚══════════════════════════════════════╝",
    ]
    return "\n".join(lines)

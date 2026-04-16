# Source: utils/stats.ts
"""Session and project statistics: token usage, cost, message counts."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .model_cost import get_model_costs


@dataclass
class DailyActivity:
    date: str  # YYYY-MM-DD
    message_count: int = 0
    session_count: int = 0
    tool_call_count: int = 0


@dataclass
class DailyModelTokens:
    date: str  # YYYY-MM-DD
    tokens_by_model: Dict[str, int] = field(default_factory=dict)


@dataclass
class StreakInfo:
    current_streak: int = 0
    longest_streak: int = 0
    current_streak_start: Optional[str] = None
    longest_streak_start: Optional[str] = None
    longest_streak_end: Optional[str] = None


@dataclass
class SessionStats:
    session_id: str
    duration: int = 0  # ms
    message_count: int = 0
    timestamp: str = ""
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    model: str = ""
    cwd: str = ""


@dataclass
class ProjectStats:
    total_cost_usd: float = 0.0
    total_sessions: int = 0
    total_messages: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    daily_activity: List[DailyActivity] = field(default_factory=list)
    streak: StreakInfo = field(default_factory=StreakInfo)


def _get_today_date_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _compute_cost_from_usage(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    """Compute USD cost from token counts."""
    pricing = get_model_costs(model)
    if not pricing:
        return 0.0
    cost = (
        input_tokens * (pricing.input_tokens / 1_000_000)
        + output_tokens * (pricing.output_tokens / 1_000_000)
        + cache_read_tokens * (pricing.prompt_cache_read_tokens / 1_000_000)
        + cache_write_tokens * (pricing.prompt_cache_write_tokens / 1_000_000)
    )
    return cost


def _extract_usage_from_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Extract token usage from a transcript entry."""
    usage = entry.get("usage") or {}
    return {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
        "model": entry.get("model", ""),
    }


async def get_session_stats(
    session_id: str,
    cwd: Optional[str] = None,
    transcript_entries: Optional[List[Dict[str, Any]]] = None,
) -> SessionStats:
    """Compute stats for a single session from its transcript entries."""
    stats = SessionStats(session_id=session_id)

    if not transcript_entries:
        return stats

    message_count = 0
    total_cost = 0.0
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_write = 0
    timestamps: List[str] = []
    model = ""

    for entry in transcript_entries:
        entry_type = entry.get("type", "")
        if entry_type in ("user", "assistant"):
            message_count += 1

        if "timestamp" in entry:
            timestamps.append(entry["timestamp"])

        if entry_type == "assistant" and "usage" in entry:
            usage = _extract_usage_from_entry(entry)
            m = usage.get("model") or entry.get("model", "")
            if m:
                model = m
            inp = usage["input_tokens"]
            out = usage["output_tokens"]
            cr = usage["cache_read_input_tokens"]
            cw = usage["cache_creation_input_tokens"]
            total_input += inp
            total_output += out
            total_cache_read += cr
            total_cache_write += cw
            total_cost += _compute_cost_from_usage(model, inp, out, cr, cw)

    stats.message_count = message_count
    stats.cost_usd = total_cost
    stats.input_tokens = total_input
    stats.output_tokens = total_output
    stats.cache_read_tokens = total_cache_read
    stats.cache_write_tokens = total_cache_write
    stats.model = model

    if timestamps:
        stats.timestamp = timestamps[0]
        if len(timestamps) > 1:
            t0 = datetime.fromisoformat(timestamps[0].replace("Z", "+00:00"))
            t1 = datetime.fromisoformat(timestamps[-1].replace("Z", "+00:00"))
            stats.duration = int((t1 - t0).total_seconds() * 1000)

    return stats


async def get_today_stats(projects_dir: Optional[str] = None) -> Dict[str, Any]:
    """Return aggregated stats for today. Stub implementation."""
    today = _get_today_date_string()
    return {
        "date": today,
        "total_cost_usd": 0.0,
        "total_sessions": 0,
        "total_messages": 0,
        "total_input_tokens": 0,
        "total_output_tokens": 0,
    }


async def get_project_stats(cwd: str) -> ProjectStats:
    """Return aggregated stats for a project directory. Stub."""
    return ProjectStats()


def calculate_streak(daily_activity: List[DailyActivity]) -> StreakInfo:
    """Calculate current and longest usage streak from daily activity."""
    if not daily_activity:
        return StreakInfo()

    dates = sorted(set(a.date for a in daily_activity if a.message_count > 0))
    if not dates:
        return StreakInfo()

    today = _get_today_date_string()
    streak = StreakInfo()

    # Calculate longest streak
    longest = 1
    longest_start = dates[0]
    longest_end = dates[0]
    cur_start = dates[0]
    cur_len = 1

    for i in range(1, len(dates)):
        prev = datetime.strptime(dates[i - 1], "%Y-%m-%d")
        curr = datetime.strptime(dates[i], "%Y-%m-%d")
        diff = (curr - prev).days
        if diff == 1:
            cur_len += 1
            if cur_len > longest:
                longest = cur_len
                longest_start = cur_start
                longest_end = dates[i]
        else:
            cur_start = dates[i]
            cur_len = 1

    streak.longest_streak = longest
    streak.longest_streak_start = longest_start
    streak.longest_streak_end = longest_end

    # Current streak (must end today or yesterday)
    if dates[-1] >= today:
        streak.current_streak = 1
        streak.current_streak_start = dates[-1]
        for i in range(len(dates) - 2, -1, -1):
            prev = datetime.strptime(dates[i], "%Y-%m-%d")
            curr = datetime.strptime(dates[i + 1], "%Y-%m-%d")
            if (curr - prev).days == 1:
                streak.current_streak += 1
                streak.current_streak_start = dates[i]
            else:
                break

    return streak

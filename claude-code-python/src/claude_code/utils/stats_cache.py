"""
Stats cache layer for Claude Code usage statistics.
Ported from statsCache.ts — avoids re-scanning JSONL files on every stats request.

Cache file: ~/.claude/stats-cache.json
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

STATS_CACHE_VERSION = 3
MIN_MIGRATABLE_VERSION = 1
STATS_CACHE_FILENAME = "stats-cache.json"


def _get_claude_home() -> Path:
    """Return ~/.claude or $CLAUDE_HOME."""
    return Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude"))


def get_stats_cache_path() -> Path:
    return _get_claude_home() / STATS_CACHE_FILENAME


# ---------------------------------------------------------------------------
# Data types (mirrors TS PersistedStatsCache)
# ---------------------------------------------------------------------------

# DailyActivity: {date, messageCount, sessionCount, toolCallCount}
DailyActivity = Dict[str, Any]
# DailyModelTokens: {date, tokensByModel: {model: int}}
DailyModelTokens = Dict[str, Any]
# ModelUsage: {inputTokens, outputTokens, cacheReadInputTokens,
#              cacheCreationInputTokens, webSearchRequests, costUSD,
#              contextWindow, maxOutputTokens}
ModelUsage = Dict[str, Any]
# SessionStats: {sessionId, timestamp, messageCount, duration, ...}
SessionStats = Dict[str, Any]


def _empty_model_usage() -> ModelUsage:
    return {
        "inputTokens": 0,
        "outputTokens": 0,
        "cacheReadInputTokens": 0,
        "cacheCreationInputTokens": 0,
        "webSearchRequests": 0,
        "costUSD": 0.0,
        "contextWindow": 0,
        "maxOutputTokens": 0,
    }


PersistedStatsCache = Dict[str, Any]


def get_empty_cache() -> PersistedStatsCache:
    return {
        "version": STATS_CACHE_VERSION,
        "lastComputedDate": None,
        "dailyActivity": [],
        "dailyModelTokens": [],
        "modelUsage": {},
        "totalSessions": 0,
        "totalMessages": 0,
        "longestSession": None,
        "firstSessionDate": None,
        "hourCounts": {},
        "totalSpeculationTimeSavedMs": 0,
        "shotDistribution": {},
    }


# ---------------------------------------------------------------------------
# Async lock
# ---------------------------------------------------------------------------

_cache_lock: Optional[asyncio.Lock] = None


def _get_lock() -> asyncio.Lock:
    global _cache_lock
    if _cache_lock is None:
        _cache_lock = asyncio.Lock()
    return _cache_lock


async def with_stats_cache_lock(coro) -> Any:
    """Execute *coro* while holding the stats-cache async lock."""
    async with _get_lock():
        return await coro


# ---------------------------------------------------------------------------
# Migration
# ---------------------------------------------------------------------------

def _migrate_stats_cache(parsed: Dict[str, Any]) -> Optional[PersistedStatsCache]:
    """
    Attempt to migrate an older cache to STATS_CACHE_VERSION.
    Returns None if the version is unknown or unmigratable.
    """
    version = parsed.get("version")
    if not isinstance(version, int):
        return None
    if version < MIN_MIGRATABLE_VERSION or version > STATS_CACHE_VERSION:
        return None
    if (
        not isinstance(parsed.get("dailyActivity"), list)
        or not isinstance(parsed.get("dailyModelTokens"), list)
        or not isinstance(parsed.get("totalSessions"), int)
        or not isinstance(parsed.get("totalMessages"), int)
    ):
        return None

    migrated: PersistedStatsCache = {
        "version": STATS_CACHE_VERSION,
        "lastComputedDate": parsed.get("lastComputedDate"),
        "dailyActivity": parsed["dailyActivity"],
        "dailyModelTokens": parsed["dailyModelTokens"],
        "modelUsage": parsed.get("modelUsage", {}),
        "totalSessions": parsed["totalSessions"],
        "totalMessages": parsed["totalMessages"],
        "longestSession": parsed.get("longestSession"),
        "firstSessionDate": parsed.get("firstSessionDate"),
        "hourCounts": parsed.get("hourCounts", {}),
        "totalSpeculationTimeSavedMs": parsed.get("totalSpeculationTimeSavedMs", 0),
        # Preserve undefined vs {} so callers can detect missing shotDistribution
        "shotDistribution": parsed.get("shotDistribution"),
    }
    return migrated


# ---------------------------------------------------------------------------
# Load / Save
# ---------------------------------------------------------------------------

async def load_stats_cache() -> PersistedStatsCache:
    """
    Load the stats cache from disk.
    Returns an empty cache if the file doesn't exist or is invalid.
    """
    cache_path = get_stats_cache_path()
    if not cache_path.exists():
        return get_empty_cache()

    try:
        content = cache_path.read_text(encoding="utf-8")
        parsed: Dict[str, Any] = json.loads(content)
    except Exception as exc:
        logger.debug("Failed to load stats cache: %s", exc)
        return get_empty_cache()

    version = parsed.get("version")

    # Exact version match — validate and return
    if version == STATS_CACHE_VERSION:
        if (
            not isinstance(parsed.get("dailyActivity"), list)
            or not isinstance(parsed.get("dailyModelTokens"), list)
            or not isinstance(parsed.get("totalSessions"), int)
            or not isinstance(parsed.get("totalMessages"), int)
        ):
            logger.debug("Stats cache has invalid structure, returning empty cache")
            return get_empty_cache()
        return parsed

    # Try migration
    migrated = _migrate_stats_cache(parsed)
    if not migrated:
        logger.debug(
            "Stats cache version %s not migratable (expected %s), returning empty cache",
            version,
            STATS_CACHE_VERSION,
        )
        return get_empty_cache()

    logger.debug("Migrated stats cache from v%s to v%s", version, STATS_CACHE_VERSION)
    await save_stats_cache(migrated)
    return migrated


async def save_stats_cache(cache: PersistedStatsCache) -> None:
    """
    Save the stats cache to disk atomically (write-to-temp + rename).
    """
    cache_path = get_stats_cache_path()

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps(cache, indent=2, ensure_ascii=False)

        # Atomic write: temp file in same directory + rename
        fd, tmp_path = tempfile.mkstemp(
            dir=cache_path.parent,
            prefix=".stats-cache-",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            os.unlink(tmp_path)
            raise

        os.replace(tmp_path, cache_path)
        logger.debug(
            "Stats cache saved (lastComputedDate: %s)", cache.get("lastComputedDate")
        )
    except Exception as exc:
        logger.error("Failed to save stats cache: %s", exc)
        # Clean up temp file if still around
        try:
            if "tmp_path" in dir():
                os.unlink(tmp_path)  # type: ignore[possibly-undefined]
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Merge helper
# ---------------------------------------------------------------------------

def merge_cache_with_new_stats(
    existing: PersistedStatsCache,
    new_stats: Dict[str, Any],
    new_last_computed_date: str,
) -> PersistedStatsCache:
    """
    Merge incremental *new_stats* into *existing* cache.

    *new_stats* keys: dailyActivity, dailyModelTokens, modelUsage,
                      sessionStats, hourCounts, totalSpeculationTimeSavedMs,
                      shotDistribution (optional).
    """
    # --- daily activity ---
    activity_map: Dict[str, DailyActivity] = {
        d["date"]: dict(d) for d in existing.get("dailyActivity", [])
    }
    for day in new_stats.get("dailyActivity", []):
        if day["date"] in activity_map:
            ex = activity_map[day["date"]]
            ex["messageCount"] = ex.get("messageCount", 0) + day.get("messageCount", 0)
            ex["sessionCount"] = ex.get("sessionCount", 0) + day.get("sessionCount", 0)
            ex["toolCallCount"] = ex.get("toolCallCount", 0) + day.get("toolCallCount", 0)
        else:
            activity_map[day["date"]] = dict(day)

    # --- daily model tokens ---
    tokens_map: Dict[str, Dict[str, int]] = {
        d["date"]: dict(d.get("tokensByModel", {}))
        for d in existing.get("dailyModelTokens", [])
    }
    for day in new_stats.get("dailyModelTokens", []):
        if day["date"] in tokens_map:
            ex_t = tokens_map[day["date"]]
            for model, count in day.get("tokensByModel", {}).items():
                ex_t[model] = ex_t.get(model, 0) + count
        else:
            tokens_map[day["date"]] = dict(day.get("tokensByModel", {}))

    # --- model usage ---
    model_usage: Dict[str, ModelUsage] = {
        k: dict(v) for k, v in existing.get("modelUsage", {}).items()
    }
    for model, usage in new_stats.get("modelUsage", {}).items():
        if model in model_usage:
            ex_u = model_usage[model]
            for key in ("inputTokens", "outputTokens", "cacheReadInputTokens",
                        "cacheCreationInputTokens", "webSearchRequests"):
                ex_u[key] = ex_u.get(key, 0) + usage.get(key, 0)
            ex_u["costUSD"] = ex_u.get("costUSD", 0.0) + usage.get("costUSD", 0.0)
            ex_u["contextWindow"] = max(
                ex_u.get("contextWindow", 0), usage.get("contextWindow", 0)
            )
            ex_u["maxOutputTokens"] = max(
                ex_u.get("maxOutputTokens", 0), usage.get("maxOutputTokens", 0)
            )
        else:
            model_usage[model] = dict(usage)

    # --- hour counts ---
    hour_counts: Dict[int, int] = dict(existing.get("hourCounts", {}))
    for hour_str, count in new_stats.get("hourCounts", {}).items():
        hour = int(hour_str)
        hour_counts[hour] = hour_counts.get(hour, 0) + count

    # --- session aggregates ---
    session_stats: List[SessionStats] = new_stats.get("sessionStats", [])
    total_sessions = existing.get("totalSessions", 0) + len(session_stats)
    total_messages = existing.get("totalMessages", 0) + sum(
        s.get("messageCount", 0) for s in session_stats
    )

    longest = existing.get("longestSession")
    for s in session_stats:
        if longest is None or s.get("duration", 0) > longest.get("duration", 0):
            longest = s

    first_date = existing.get("firstSessionDate")
    for s in session_stats:
        ts = s.get("timestamp")
        if ts and (first_date is None or ts < first_date):
            first_date = ts

    result: PersistedStatsCache = {
        "version": STATS_CACHE_VERSION,
        "lastComputedDate": new_last_computed_date,
        "dailyActivity": sorted(activity_map.values(), key=lambda d: d["date"]),
        "dailyModelTokens": sorted(
            [{"date": d, "tokensByModel": tm} for d, tm in tokens_map.items()],
            key=lambda x: x["date"],
        ),
        "modelUsage": model_usage,
        "totalSessions": total_sessions,
        "totalMessages": total_messages,
        "longestSession": longest,
        "firstSessionDate": first_date,
        "hourCounts": hour_counts,
        "totalSpeculationTimeSavedMs": (
            existing.get("totalSpeculationTimeSavedMs", 0)
            + new_stats.get("totalSpeculationTimeSavedMs", 0)
        ),
    }

    # shot distribution (optional feature)
    shot_dist = new_stats.get("shotDistribution")
    if shot_dist is not None:
        merged_shots: Dict[int, int] = dict(existing.get("shotDistribution") or {})
        for k, v in shot_dist.items():
            key = int(k)
            merged_shots[key] = merged_shots.get(key, 0) + v
        result["shotDistribution"] = merged_shots

    return result


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def to_date_string(dt: datetime) -> str:
    """Return 'YYYY-MM-DD' for *dt*."""
    return dt.strftime("%Y-%m-%d")


def get_today_date_string() -> str:
    return to_date_string(datetime.now())


def get_yesterday_date_string() -> str:
    from datetime import timedelta
    return to_date_string(datetime.now() - timedelta(days=1))


def is_date_before(date1: str, date2: str) -> bool:
    """True if *date1* < *date2* (both YYYY-MM-DD)."""
    return date1 < date2

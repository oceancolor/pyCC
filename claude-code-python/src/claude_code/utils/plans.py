# Source: utils/plans.ts
"""Plan file management for plan mode sessions."""
from __future__ import annotations

import os
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Optional

from .env_utils import get_claude_config_home_dir

# Per-session slug cache: session_id -> slug
_plan_slug_cache: dict[str, str] = {}
MAX_SLUG_RETRIES = 10

ADJECTIVES = [
    "amber", "bold", "calm", "deft", "epic", "firm", "glad", "hale",
    "idle", "just", "keen", "lush", "mute", "neat", "open", "pure",
    "quick", "rich", "safe", "tall", "used", "vast", "warm", "zeal",
]
NOUNS = [
    "arch", "bear", "cave", "dawn", "edge", "fern", "gust", "hill",
    "iris", "jade", "kelp", "lark", "mist", "noon", "opal", "pine",
    "quay", "reef", "sage", "tide", "urn", "vale", "wave", "yew",
]


def generate_word_slug() -> str:
    """Generate a random two-word slug."""
    import random
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    return f"{adj}-{noun}"


@lru_cache(maxsize=1)
def get_plans_directory() -> str:
    """Return the plans directory, creating it if needed."""
    config_home = get_claude_config_home_dir()
    plans_dir = os.path.join(config_home, "plans")
    os.makedirs(plans_dir, exist_ok=True)
    return plans_dir


def get_plan_slug(session_id: Optional[str] = None) -> str:
    """Get or generate a word slug for the current session's plan."""
    sid = session_id or "default"
    if sid in _plan_slug_cache:
        return _plan_slug_cache[sid]

    plans_dir = get_plans_directory()
    slug: Optional[str] = None
    for _ in range(MAX_SLUG_RETRIES):
        candidate = generate_word_slug()
        file_path = os.path.join(plans_dir, f"{candidate}.md")
        if not os.path.exists(file_path):
            slug = candidate
            break
    if not slug:
        slug = generate_word_slug()

    _plan_slug_cache[sid] = slug
    return slug


def set_plan_slug(session_id: str, slug: str) -> None:
    """Set a specific plan slug for a session (used when resuming)."""
    _plan_slug_cache[session_id] = slug


def clear_plan_slug(session_id: Optional[str] = None) -> None:
    """Clear the plan slug for the current session."""
    sid = session_id or "default"
    _plan_slug_cache.pop(sid, None)


def clear_all_plan_slugs() -> None:
    """Clear ALL plan slug entries."""
    _plan_slug_cache.clear()


def get_plan_file_path(session_id: Optional[str] = None, agent_id: Optional[str] = None) -> Optional[str]:
    """Return the plan file path for the given session."""
    sid = session_id or agent_id or "default"
    slug = get_plan_slug(sid)
    plans_dir = get_plans_directory()
    return os.path.join(plans_dir, f"{slug}.md")


def get_plan(session_id: Optional[str] = None, agent_id: Optional[str] = None) -> Optional[str]:
    """Read and return the current plan content, or None if not found."""
    file_path = get_plan_file_path(session_id=session_id, agent_id=agent_id)
    if not file_path or not os.path.exists(file_path):
        return None
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        return content if content.strip() else None
    except OSError:
        return None


async def save_plan(
    content: str,
    session_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> str:
    """Write plan content to disk. Returns the file path."""
    import asyncio
    file_path = get_plan_file_path(session_id=session_id, agent_id=agent_id)
    if not file_path:
        raise ValueError("Cannot determine plan file path")

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _write_plan_sync, file_path, content)
    return file_path


def _write_plan_sync(file_path: str, content: str) -> None:
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)


async def persist_file_snapshot_if_remote() -> None:
    """Stub: persist plan snapshot for remote sessions (CCR). No-op locally."""
    pass

"""Skills utilities. Ported from utils/skills/."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

FILE_STABILITY_THRESHOLD_MS = 1000
RELOAD_DEBOUNCE_MS = 300

# Module-level change listeners
_change_listeners: List[Callable[[], None]] = []
_skill_dir_watcher: Optional[asyncio.Task] = None  # type: ignore[type-arg]
_last_watched_paths: List[str] = []


def get_skills_path() -> Optional[str]:
    """Return the primary skills directory path, or None if not configured."""
    env_path = os.environ.get("CLAUDE_CODE_SKILLS_PATH")
    if env_path:
        return env_path

    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir

        return os.path.join(get_claude_config_home_dir(), "skills")
    except Exception:
        return str(Path.home() / ".claude" / "skills")


def get_available_skills() -> List[dict]:
    """Return a list of available skills from the skills directory.

    Each entry is a dict with at least ``name`` (str) and ``path`` (str).
    Returns an empty list if the skills directory does not exist or is empty.
    """
    skills_path = get_skills_path()
    if not skills_path or not os.path.isdir(skills_path):
        return []

    skills: List[dict] = []
    try:
        for entry in sorted(os.scandir(skills_path), key=lambda e: e.name):
            if not entry.is_dir():
                continue
            skill_dir = entry.path
            skill_md = os.path.join(skill_dir, "SKILL.md")
            if not os.path.isfile(skill_md):
                continue
            skills.append(
                {
                    "name": entry.name,
                    "path": skill_dir,
                    "skill_md": skill_md,
                }
            )
    except OSError:
        pass

    return skills


def clear_skill_caches() -> None:
    """Invalidate any in-memory skill caches."""
    # Future caches can be added here
    pass


def on_dynamic_skills_loaded(listener: Callable[[], None]) -> Callable[[], None]:
    """Register a listener to be called whenever skills are reloaded.

    Returns an unsubscribe function.
    """
    _change_listeners.append(listener)

    def unsubscribe() -> None:
        try:
            _change_listeners.remove(listener)
        except ValueError:
            pass

    return unsubscribe


def _notify_skill_change_listeners() -> None:
    """Notify all registered skill-change listeners."""
    for listener in list(_change_listeners):
        try:
            listener()
        except Exception:
            pass


async def start_watching_skill_directories(paths: Optional[List[str]] = None) -> None:
    """Begin watching skill directories for file changes and trigger reloads.

    Args:
        paths: List of directories to watch. Defaults to the primary skills path.
    """
    global _skill_dir_watcher, _last_watched_paths

    watch_paths = paths or []
    if not watch_paths:
        p = get_skills_path()
        if p:
            watch_paths = [p]

    _last_watched_paths = watch_paths

    async def _poll_and_watch() -> None:
        mtimes: Dict[str, float] = {}

        async def _snapshot() -> Dict[str, float]:
            result: Dict[str, float] = {}
            for d in _last_watched_paths:
                try:
                    for entry in Path(d).rglob("*"):
                        if entry.is_file():
                            result[str(entry)] = entry.stat().st_mtime
                except Exception:
                    pass
            return result

        mtimes = await asyncio.get_event_loop().run_in_executor(None, lambda: {})
        mtimes = await _snapshot()

        debounce_task: Optional[asyncio.TimerHandle] = None

        def _schedule_reload() -> None:
            nonlocal debounce_task
            if debounce_task:
                debounce_task.cancel()

            def _do_reload() -> None:
                clear_skill_caches()
                _notify_skill_change_listeners()

            loop = asyncio.get_event_loop()
            debounce_task = loop.call_later(RELOAD_DEBOUNCE_MS / 1000, _do_reload)

        while True:
            await asyncio.sleep(2.0)
            new_mtimes = await _snapshot()
            if new_mtimes != mtimes:
                mtimes = new_mtimes
                _schedule_reload()

    _skill_dir_watcher = asyncio.ensure_future(_poll_and_watch())


def stop_watching_skill_directories() -> None:
    """Stop watching skill directories."""
    global _skill_dir_watcher
    if _skill_dir_watcher:
        _skill_dir_watcher.cancel()
        _skill_dir_watcher = None

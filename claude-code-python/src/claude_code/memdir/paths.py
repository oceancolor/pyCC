"""
Auto-memory directory path resolution.
Ported from memdir/paths.ts
"""
from __future__ import annotations

import os
import re
import sys
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import Optional

AUTO_MEM_DIRNAME = "memory"
AUTO_MEM_ENTRYPOINT_NAME = "MEMORY.md"


# ─── Environment helpers ────────────────────────────────────────────────────

def _is_env_truthy(val: Optional[str]) -> bool:
    return val is not None and val.lower() in ("1", "true", "yes", "on")


def _is_env_defined_falsy(val: Optional[str]) -> bool:
    return val is not None and val.lower() in ("0", "false", "no", "off")


def _get_claude_config_home_dir() -> str:
    try:
        from claude_code.utils.env_utils import get_claude_config_home_dir  # type: ignore
        return get_claude_config_home_dir()
    except ImportError:
        return os.environ.get(
            "CLAUDE_CONFIG_DIR",
            os.path.join(os.path.expanduser("~"), ".claude"),
        )


def _get_project_root() -> str:
    try:
        from claude_code.bootstrap.state import get_project_root  # type: ignore
        return get_project_root()
    except ImportError:
        return os.getcwd()


def _get_is_non_interactive_session() -> bool:
    try:
        from claude_code.bootstrap.state import get_is_non_interactive_session  # type: ignore
        return get_is_non_interactive_session()
    except ImportError:
        return bool(os.environ.get("CLAUDE_CODE_NON_INTERACTIVE"))


def _get_feature_value(key: str, default: bool) -> bool:
    try:
        from claude_code.services.analytics.growthbook import (  # type: ignore
            get_feature_value_cached_may_be_stale,
        )
        return get_feature_value_cached_may_be_stale(key, default)
    except ImportError:
        return default


def _find_canonical_git_root(path: str) -> Optional[str]:
    try:
        from claude_code.utils.git import find_canonical_git_root  # type: ignore
        return find_canonical_git_root(path)
    except ImportError:
        return None


def _sanitize_path(path: str) -> str:
    try:
        from claude_code.utils.path import sanitize_path  # type: ignore
        return sanitize_path(path)
    except ImportError:
        # Fallback: replace path separators and colons
        return re.sub(r"[/\\:]", "_", path).strip("_")


def _get_initial_settings() -> dict:
    try:
        from claude_code.utils.settings.settings import get_initial_settings  # type: ignore
        return get_initial_settings() or {}
    except ImportError:
        return {}


def _get_settings_for_source(source: str) -> Optional[dict]:
    try:
        from claude_code.utils.settings.settings import get_settings_for_source  # type: ignore
        return get_settings_for_source(source)
    except ImportError:
        return None


# ─── Public API ─────────────────────────────────────────────────────────────

def is_auto_memory_enabled() -> bool:
    """Return True if auto-memory features are enabled."""
    env_val = os.environ.get("CLAUDE_CODE_DISABLE_AUTO_MEMORY")
    if _is_env_truthy(env_val):
        return False
    if _is_env_defined_falsy(env_val):
        return True

    if _is_env_truthy(os.environ.get("CLAUDE_CODE_SIMPLE")):
        return False

    if _is_env_truthy(os.environ.get("CLAUDE_CODE_REMOTE")) and not os.environ.get(
        "CLAUDE_CODE_REMOTE_MEMORY_DIR"
    ):
        return False

    settings = _get_initial_settings()
    if settings.get("autoMemoryEnabled") is not None:
        return bool(settings["autoMemoryEnabled"])

    return True


def is_extract_mode_active() -> bool:
    """Return True if the extract-memories background agent should run."""
    if not _get_feature_value("tengu_passport_quail", False):
        return False
    return not _get_is_non_interactive_session() or _get_feature_value(
        "tengu_slate_thimble", False
    )


def get_memory_base_dir() -> str:
    """Return base directory for persistent memory storage."""
    override = os.environ.get("CLAUDE_CODE_REMOTE_MEMORY_DIR")
    if override:
        return override
    return _get_claude_config_home_dir()


def _validate_memory_path(
    raw: Optional[str],
    expand_tilde: bool,
) -> Optional[str]:
    """Validate and normalize a candidate auto-memory directory path."""
    if not raw:
        return None

    candidate = raw
    if expand_tilde and (candidate.startswith("~/") or candidate.startswith("~\\")):
        rest = candidate[2:]
        rest_norm = os.path.normpath(rest or ".")
        if rest_norm in (".", ".."):
            return None
        candidate = os.path.join(os.path.expanduser("~"), rest)

    normalized = os.path.normpath(candidate).rstrip("/\\")

    if not os.path.isabs(normalized):
        return None
    if len(normalized) < 3:
        return None
    if re.match(r"^[A-Za-z]:$", normalized):
        return None
    if normalized.startswith("\\\\") or normalized.startswith("//"):
        return None
    if "\0" in normalized:
        return None

    return (normalized + os.sep)


def _get_auto_mem_path_override() -> Optional[str]:
    return _validate_memory_path(
        os.environ.get("CLAUDE_COWORK_MEMORY_PATH_OVERRIDE"),
        False,
    )


def _get_auto_mem_path_setting() -> Optional[str]:
    dir_path = (
        (_get_settings_for_source("policySettings") or {}).get("autoMemoryDirectory")
        or (_get_settings_for_source("flagSettings") or {}).get("autoMemoryDirectory")
        or (_get_settings_for_source("localSettings") or {}).get("autoMemoryDirectory")
        or (_get_settings_for_source("userSettings") or {}).get("autoMemoryDirectory")
    )
    return _validate_memory_path(dir_path, True)


def has_auto_mem_path_override() -> bool:
    """Return True if CLAUDE_COWORK_MEMORY_PATH_OVERRIDE is set to a valid override."""
    return _get_auto_mem_path_override() is not None


def _get_auto_mem_base() -> str:
    project_root = _get_project_root()
    return _find_canonical_git_root(project_root) or project_root


# Memoized: keyed on project root
_auto_mem_path_cache: dict = {}


def get_auto_mem_path() -> str:
    """Return the auto-memory directory path."""
    project_root = _get_project_root()
    if project_root in _auto_mem_path_cache:
        return _auto_mem_path_cache[project_root]

    override = _get_auto_mem_path_override() or _get_auto_mem_path_setting()
    if override:
        result = override
    else:
        projects_dir = os.path.join(get_memory_base_dir(), "projects")
        result = os.path.join(
            projects_dir, _sanitize_path(_get_auto_mem_base()), AUTO_MEM_DIRNAME
        ) + os.sep

    _auto_mem_path_cache[project_root] = result
    return result


def clear_auto_mem_path_cache() -> None:
    """Clear the memoized auto-memory path cache (for testing)."""
    _auto_mem_path_cache.clear()


def get_auto_mem_daily_log_path(date=None) -> str:
    """Return the daily log file path for the given date (defaults to today)."""
    from datetime import date as _date

    d = date or _date.today()
    yyyy = str(d.year)
    mm = f"{d.month:02d}"
    dd = f"{d.day:02d}"
    return os.path.join(
        get_auto_mem_path(), "logs", yyyy, mm, f"{yyyy}-{mm}-{dd}.md"
    )


def get_auto_mem_entrypoint() -> str:
    """Return the auto-memory entrypoint (MEMORY.md)."""
    return os.path.join(get_auto_mem_path(), AUTO_MEM_ENTRYPOINT_NAME)


def is_auto_mem_path(absolute_path: str) -> bool:
    """Return True if *absolute_path* is within the auto-memory directory."""
    normalized = os.path.normpath(absolute_path)
    return normalized.startswith(get_auto_mem_path())

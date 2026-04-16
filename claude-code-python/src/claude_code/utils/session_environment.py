"""
Session environment management utilities.
Port of sessionEnvironment.ts — manage hook-sourced shell environment scripts
that persist per-session environment state across shell commands.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Hook ordering constants
# ---------------------------------------------------------------------------

_HOOK_ENV_PRIORITY: dict[str, int] = {
    "setup": 0,
    "sessionstart": 1,
    "cwdchanged": 2,
    "filechanged": 3,
}

_HOOK_ENV_REGEX = re.compile(
    r"^(setup|sessionstart|cwdchanged|filechanged)-hook-(\d+)\.sh$"
)

# ---------------------------------------------------------------------------
# Cache (module-level, mirrors TS module-scope variable)
#
#   _UNSET   → not yet loaded
#   None     → loaded, nothing found
#   str      → loaded script content
# ---------------------------------------------------------------------------

_UNSET = object()
_session_env_script: object = _UNSET  # str | None | _UNSET


def _get_claude_config_home() -> Path:
    """Return the Claude config home directory."""
    env_dir = os.environ.get("CLAUDE_CONFIG_DIR")
    if env_dir:
        return Path(env_dir)
    return Path.home() / ".claude"


def _get_session_id() -> str:
    """Return a stable session identifier (PID-based fallback)."""
    return os.environ.get("CLAUDE_SESSION_ID", f"pid-{os.getpid()}")


# ---------------------------------------------------------------------------
# Public path helpers
# ---------------------------------------------------------------------------

def get_session_env_dir_path() -> Path:
    """Return (and create) the per-session hook env directory."""
    session_env_dir = _get_claude_config_home() / "session-env" / _get_session_id()
    session_env_dir.mkdir(parents=True, exist_ok=True)
    return session_env_dir


def get_hook_env_file_path(
    hook_event: str,   # 'Setup' | 'SessionStart' | 'CwdChanged' | 'FileChanged'
    hook_index: int,
) -> Path:
    """Return the path for a specific hook's env script file."""
    prefix = hook_event.lower()
    return get_session_env_dir_path() / f"{prefix}-hook-{hook_index}.sh"


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------

def invalidate_session_env_cache() -> None:
    """Force the next call to :func:`get_session_environment_script` to
    re-read from disk."""
    global _session_env_script
    logger.debug("Invalidating session environment cache")
    _session_env_script = _UNSET


def clear_cwd_env_files() -> None:
    """Blank out cwdchanged/filechanged hook env files for the current session."""
    try:
        session_dir = get_session_env_dir_path()
        for f in session_dir.iterdir():
            if _HOOK_ENV_REGEX.match(f.name) and (
                f.name.startswith("filechanged-hook-")
                or f.name.startswith("cwdchanged-hook-")
            ):
                f.write_text("")
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("Failed to clear cwd env files: %s", exc)


# ---------------------------------------------------------------------------
# Main accessor
# ---------------------------------------------------------------------------

def get_session_environment_script() -> Optional[str]:
    """Return the merged shell environment script for this session, or *None*.

    The result is cached after the first successful load.
    """
    global _session_env_script

    if os.name == "nt":
        logger.debug("Session environment not yet supported on Windows")
        return None

    if _session_env_script is not _UNSET:
        return _session_env_script  # type: ignore[return-value]

    scripts: list[str] = []

    # 1. CLAUDE_ENV_FILE passed from parent process (e.g. venv activation)
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if env_file:
        try:
            env_script = Path(env_file).read_text("utf-8").strip()
            if env_script:
                scripts.append(env_script)
                logger.debug(
                    "Session environment loaded from CLAUDE_ENV_FILE: %s (%d chars)",
                    env_file, len(env_script),
                )
        except FileNotFoundError:
            pass
        except Exception as exc:
            logger.debug("Failed to read CLAUDE_ENV_FILE: %s", exc)

    # 2. Hook env files from session directory
    session_env_dir = get_session_env_dir_path()
    try:
        hook_files = sorted(
            [f.name for f in session_env_dir.iterdir() if _HOOK_ENV_REGEX.match(f.name)],
            key=_sort_key,
        )
        for fname in hook_files:
            fpath = session_env_dir / fname
            try:
                content = fpath.read_text("utf-8").strip()
                if content:
                    scripts.append(content)
            except FileNotFoundError:
                pass
            except Exception as exc:
                logger.debug("Failed to read hook file %s: %s", fpath, exc)

        if hook_files:
            logger.debug(
                "Session environment loaded from %d hook file(s)", len(hook_files)
            )
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("Failed to load session environment from hooks: %s", exc)

    if not scripts:
        logger.debug("No session environment scripts found")
        _session_env_script = None
        return None

    _session_env_script = "\n".join(scripts)
    logger.debug(
        "Session environment script ready (%d chars total)", len(_session_env_script)
    )
    return _session_env_script  # type: ignore[return-value]


def _sort_key(filename: str) -> tuple[int, int]:
    m = _HOOK_ENV_REGEX.match(filename)
    if not m:
        return (99, 0)
    hook_type = m.group(1)
    hook_index = int(m.group(2))
    return (_HOOK_ENV_PRIORITY.get(hook_type, 99), hook_index)

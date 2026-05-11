"""Git-related behaviors that depend on user settings.
Ported from utils/gitSettings.ts.

Kept separate from git.py for the same reason as the TypeScript original:
this module imports settings which has a heavy transitive dependency chain.
"""
from __future__ import annotations
import os


def _is_env_truthy(val: str | None) -> bool:
    return (val or "").lower() in ("1", "true", "yes")


def _is_env_defined_falsy(val: str | None) -> bool:
    return val is not None and (val or "").lower() in ("0", "false", "no")


def should_include_git_instructions() -> bool:
    """Return True if the agent should include git instructions in its system prompt.

    Checks ``CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS`` first (env override),
    then falls back to the ``includeGitInstructions`` setting.
    """
    env_val = os.environ.get("CLAUDE_CODE_DISABLE_GIT_INSTRUCTIONS")
    if _is_env_truthy(env_val):
        return False
    if _is_env_defined_falsy(env_val):
        return True

    try:
        from claude_code.utils.settings.settings import get_initial_settings  # type: ignore[import]
        settings = get_initial_settings() or {}
        return settings.get("includeGitInstructions", True)
    except Exception:
        return True

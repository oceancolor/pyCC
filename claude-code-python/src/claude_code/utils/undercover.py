"""
undercover.py - Undercover mode utilities.

Ported from undercover.ts.

In the external (non-Anthropic) build USER_TYPE is never 'ant', so all
functions reduce to trivial no-op / False / '' returns — exactly as the TS
bundler dead-code-eliminates the ant-only branches.

Activation (ant builds only):
  - CLAUDE_CODE_UNDERCOVER=1  → force ON
  - Otherwise AUTO: ON unless the repo remote is on the internal allowlist
    ('internal' repo class).  Safe default is ON.
  - No force-OFF path.
"""

from __future__ import annotations

import os


def _is_env_truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in ("1", "true", "yes")


def _get_repo_class_cached() -> str:
    """
    Stub for getRepoClassCached().  Returns 'external' so that, in tests or
    when running outside a git repo, undercover defaults to ON for ant users.
    Real implementation would check the git remote against an allowlist.
    """
    return "external"


def is_undercover() -> bool:
    """
    Return True when undercover mode is active.

    For non-ant builds (USER_TYPE != 'ant') always returns False.
    For ant builds: True if CLAUDE_CODE_UNDERCOVER is set, or if the repo
    class is not 'internal'.
    """
    if os.environ.get("USER_TYPE") == "ant":
        if _is_env_truthy(os.environ.get("CLAUDE_CODE_UNDERCOVER")):
            return True
        return _get_repo_class_cached() != "internal"
    return False


def get_undercover_instructions() -> str:
    """
    Return the undercover mode instructions string for ant builds.
    Returns empty string in external builds.
    """
    if os.environ.get("USER_TYPE") == "ant":
        return (
            "## UNDERCOVER MODE — CRITICAL\n\n"
            "You are operating UNDERCOVER in a PUBLIC/OPEN-SOURCE repository. "
            "Your commit messages, PR titles, and PR bodies MUST NOT contain ANY "
            "Anthropic-internal information. Do not blow your cover.\n\n"
            "NEVER include in commit messages or PR descriptions:\n"
            "- Internal model codenames (animal names like Capybara, Tengu, etc.)\n"
            "- Unreleased model version numbers (e.g., opus-4-7, sonnet-4-8)\n"
            "- Internal repo or project names (e.g., claude-cli-internal, anthropics/…)\n"
            "- Internal tooling, Slack channels, or short links (e.g., go/cc, #claude-code-…)\n"
            "- The phrase \"Claude Code\" or any mention that you are an AI\n"
            "- Any hint of what model or version you are\n"
            "- Co-Authored-By lines or any other attribution\n\n"
            "Write commit messages as a human developer would — describe only what "
            "the code change does.\n"
        )
    return ""


def should_show_undercover_auto_notice() -> bool:
    """
    True when: ant build, undercover is active via auto-detection (not forced
    via env), and the user hasn't seen the notice before.

    Simplified: always returns False in external builds and when forced via env.
    The 'hasSeenUndercoverAutoNotice' check is omitted (no global config here).
    """
    if os.environ.get("USER_TYPE") == "ant":
        if _is_env_truthy(os.environ.get("CLAUDE_CODE_UNDERCOVER")):
            return False
        if not is_undercover():
            return False
        return True
    return False

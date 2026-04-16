"""Project onboarding state. Ported from projectOnboardingState.ts"""
from __future__ import annotations
import os
from functools import lru_cache
from typing import TypedDict


class Step(TypedDict):
    key: str
    text: str
    is_complete: bool
    is_completable: bool
    is_enabled: bool


def get_steps() -> list:
    cwd = os.getcwd()
    has_claude_md = os.path.exists(os.path.join(cwd, "CLAUDE.md"))
    is_empty = not any(os.scandir(cwd))
    return [
        {
            "key": "workspace",
            "text": "Ask Claude to create a new app or clone a repository",
            "is_complete": False,
            "is_completable": True,
            "is_enabled": is_empty,
        },
        {
            "key": "claudemd",
            "text": "Run /init to create a CLAUDE.md file with instructions for Claude",
            "is_complete": has_claude_md,
            "is_completable": True,
            "is_enabled": not is_empty,
        },
    ]


def is_project_onboarding_complete() -> bool:
    return all(
        s["is_complete"]
        for s in get_steps()
        if s["is_completable"] and s["is_enabled"]
    )


def maybe_mark_project_onboarding_complete() -> None:
    from claude_code.utils.config import get_current_project_config, save_current_project_config
    config = get_current_project_config()
    if config.get("hasCompletedProjectOnboarding"):
        return
    if is_project_onboarding_complete():
        save_current_project_config(lambda c: {**c, "hasCompletedProjectOnboarding": True})


@lru_cache(maxsize=1)
def should_show_project_onboarding() -> bool:
    from claude_code.utils.config import get_current_project_config
    config = get_current_project_config()
    if (config.get("hasCompletedProjectOnboarding")
            or config.get("projectOnboardingSeenCount", 0) >= 4
            or os.environ.get("IS_DEMO")):
        return False
    return not is_project_onboarding_complete()


def increment_project_onboarding_seen_count() -> None:
    from claude_code.utils.config import save_current_project_config
    save_current_project_config(
        lambda c: {**c, "projectOnboardingSeenCount": c.get("projectOnboardingSeenCount", 0) + 1}
    )

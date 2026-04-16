"""
Common constants and date utilities
原始 TS: src/constants/common.ts

lodash memoize → functools.lru_cache
"""
from __future__ import annotations

import os
from datetime import datetime
from functools import lru_cache


def get_local_iso_date() -> str:
    """
    Returns the LOCAL date in ISO format (YYYY-MM-DD).
    Respects CLAUDE_CODE_OVERRIDE_DATE environment variable.
    """
    override = os.environ.get("CLAUDE_CODE_OVERRIDE_DATE")
    if override:
        return override

    now = datetime.now()
    return now.strftime("%Y-%m-%d")


@lru_cache(maxsize=1)
def get_session_start_date() -> str:
    """
    Memoized for prompt-cache stability — captures the date once at session start.
    原始 TS: getSessionStartDate = memoize(getLocalISODate)
    """
    return get_local_iso_date()


def get_local_month_year() -> str:
    """
    Returns 'Month YYYY' (e.g. 'February 2026') in the user's local timezone.
    Changes monthly, not daily — used in tool prompts to minimize cache busting.
    """
    override = os.environ.get("CLAUDE_CODE_OVERRIDE_DATE")
    if override:
        date = datetime.fromisoformat(override)
    else:
        date = datetime.now()
    return date.strftime("%B %Y")

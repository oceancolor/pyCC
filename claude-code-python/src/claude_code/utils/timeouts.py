"""
Timeouts constants for bash operations. Ported from timeouts.ts
"""
from __future__ import annotations
import os
from typing import Optional

DEFAULT_TIMEOUT_MS = 120_000  # 2 minutes
MAX_TIMEOUT_MS = 600_000      # 10 minutes


def get_default_bash_timeout_ms(env: Optional[dict] = None) -> int:
    e = env if env is not None else dict(os.environ)
    val = e.get("BASH_DEFAULT_TIMEOUT_MS")
    if val:
        try:
            parsed = int(val)
            if parsed > 0:
                return parsed
        except ValueError:
            pass
    return DEFAULT_TIMEOUT_MS


def get_max_bash_timeout_ms(env: Optional[dict] = None) -> int:
    e = env if env is not None else dict(os.environ)
    val = e.get("BASH_MAX_TIMEOUT_MS")
    if val:
        try:
            parsed = int(val)
            if parsed > 0:
                return max(parsed, get_default_bash_timeout_ms(e))
        except ValueError:
            pass
    return max(MAX_TIMEOUT_MS, get_default_bash_timeout_ms(e))

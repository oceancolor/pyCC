"""Warning handler - Python port of warningHandler.ts.

Provides a centralised, de-duplicating warning handler with an optional
occurrence-count tracker, mirroring the Node.js process 'warning' event logic.
"""

from __future__ import annotations

import os
import re
import warnings
from collections import defaultdict
from typing import Optional

MAX_WARNING_KEYS = 1000

# Internal warning patterns to suppress from users
_INTERNAL_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r'MaxListenersExceededWarning.*AbortSignal'),
    re.compile(r'MaxListenersExceededWarning.*EventTarget'),
]


def _is_internal_warning(message: str) -> bool:
    return any(p.search(message) for p in _INTERNAL_PATTERNS)


class WarningHandler:
    """Centralised warning manager.

    * Deduplicates warnings by a short key (category + first 50 chars).
    * Caps unique keys at MAX_WARNING_KEYS to prevent memory growth.
    * Optionally suppresses internal/noisy warnings.
    """

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._messages: list[str] = []

    def add_warning(self, message: str, category: str = 'UserWarning') -> None:
        """Record a warning, deduplicating by key."""
        key = f'{category}: {message[:50]}'
        count = self._counts.get(key, 0)

        if key in self._counts or len(self._counts) < MAX_WARNING_KEYS:
            self._counts[key] = count + 1

        if not _is_internal_warning(f'{category}: {message}'):
            self._messages.append(message)

    def get_warnings(self) -> list[str]:
        """Return all recorded (non-internal) warning messages."""
        return list(self._messages)

    def clear(self) -> None:
        """Clear all recorded warnings and counts."""
        self._counts.clear()
        self._messages.clear()

    def get_count(self, message: str, category: str = 'UserWarning') -> int:
        """Return the occurrence count for a warning key."""
        key = f'{category}: {message[:50]}'
        return self._counts.get(key, 0)


# Module-level singleton (mirrors TS module-level warningCounts map)
_handler = WarningHandler()


def warn(message: str, category: str = 'UserWarning') -> None:
    """Record and (if not internal) emit a Python warning."""
    _handler.add_warning(message, category)
    if not _is_internal_warning(f'{category}: {message}'):
        debug = os.environ.get('CLAUDE_DEBUG', '')
        if debug and debug.lower() not in ('0', 'false', 'no'):
            warnings.warn(message, stacklevel=2)


def get_warning_handler() -> WarningHandler:
    """Return the module-level WarningHandler singleton."""
    return _handler


def reset_warning_handler() -> None:
    """Testing-only reset of the module-level handler."""
    _handler.clear()


def initialize_warning_handler() -> None:
    """No-op shim for API compatibility with the TS version.

    In Python, warnings are handled via the warnings module rather than
    process-level event listeners.
    """

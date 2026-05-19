"""Compact service.

Provides context-window compaction utilities:

- ``compact_messages`` — compress a list of messages to a shorter summary.
- ``auto_compact_if_needed`` — automatically compact when the context
  window exceeds a configured threshold.
- ``is_auto_compact_enabled`` — check whether auto-compaction is on.
- ``reset_microcompact_state`` — reset the micro-compact bookkeeping.
- ``run_post_compact_cleanup`` — perform cleanup tasks after compaction.

Ported from: src/services/compact/ (TypeScript)

Usage::

    from claude_code.services.compact import compact_messages, auto_compact_if_needed
"""
from __future__ import annotations

from claude_code.services.compact.compact import compact_messages
from claude_code.services.compact.auto_compact import (
    auto_compact_if_needed,
    is_auto_compact_enabled,
)
from claude_code.services.compact.micro_compact import reset_microcompact_state
from claude_code.services.compact.post_compact_cleanup import run_post_compact_cleanup

__all__ = [
    "compact_messages",
    "auto_compact_if_needed",
    "is_auto_compact_enabled",
    "reset_microcompact_state",
    "run_post_compact_cleanup",
]

"""
Auto-dream background memory consolidation.
Ported from services/autoDream/autoDream.ts (324 lines)

Background memory consolidation. Fires the /dream prompt as a forked
subagent when time-gate passes AND enough sessions have accumulated.

Gate order (cheapest first):
  1. Time: hours since lastConsolidatedAt >= minHours (one stat)
  2. Sessions: transcript count with mtime > lastConsolidatedAt >= minSessions
  3. Lock: no other process mid-consolidation
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .config import is_auto_dream_enabled
from .consolidation_lock import (
    list_sessions_touched_since,
    read_last_consolidated_at,
    rollback_consolidation_lock,
    try_acquire_consolidation_lock,
)
from .consolidation_prompt import build_consolidation_prompt

logger = logging.getLogger(__name__)

# Scan throttle: when time-gate passes but session-gate doesn't, the lock
# mtime doesn't advance, so the time-gate keeps passing every turn.
SESSION_SCAN_INTERVAL_MS = 10 * 60 * 1000  # 10 minutes


@dataclass
class AutoDreamConfig:
    min_hours: float = 24.0
    min_sessions: int = 5


DEFAULTS = AutoDreamConfig()


def _get_config() -> AutoDreamConfig:
    """
    Read configuration from environment variables (simplified — real impl uses GrowthBook).
    """
    try:
        min_hours = float(os.environ.get("CLAUDE_CODE_DREAM_MIN_HOURS", str(DEFAULTS.min_hours)))
        if min_hours <= 0:
            min_hours = DEFAULTS.min_hours
    except (ValueError, TypeError):
        min_hours = DEFAULTS.min_hours

    try:
        min_sessions = int(os.environ.get("CLAUDE_CODE_DREAM_MIN_SESSIONS", str(DEFAULTS.min_sessions)))
        if min_sessions <= 0:
            min_sessions = DEFAULTS.min_sessions
    except (ValueError, TypeError):
        min_sessions = DEFAULTS.min_sessions

    return AutoDreamConfig(min_hours=min_hours, min_sessions=min_sessions)


def _is_gate_open() -> bool:
    """Check all feature gates before running auto-dream."""
    # Skip in remote mode
    if os.environ.get("CLAUDE_CODE_REMOTE_MODE", "").lower() in ("1", "true"):
        return False
    # Check auto-memory enabled
    if not _is_auto_memory_enabled():
        return False
    return is_auto_dream_enabled()


def _is_auto_memory_enabled() -> bool:
    return os.environ.get("CLAUDE_CODE_AUTO_MEMORY", "").lower() in ("1", "true")


def _get_auto_mem_path() -> str:
    return os.environ.get(
        "CLAUDE_CODE_AUTO_MEM_PATH",
        os.path.join(os.path.expanduser("~"), ".claude", "memory"),
    )


def _get_session_id() -> Optional[str]:
    return os.environ.get("CLAUDE_CODE_SESSION_ID")


def _get_transcript_dir() -> str:
    cwd = os.environ.get("CLAUDE_CODE_CWD", os.getcwd())
    project_key = cwd.replace("/", "_").lstrip("_")
    return os.path.join(os.path.expanduser("~"), ".claude", "projects", project_key)


# ---------------------------------------------------------------------------
# Module-level runner (closure-scoped in TS; module-level here)
# ---------------------------------------------------------------------------

_runner: Optional[Callable] = None


def init_auto_dream() -> None:
    """
    Initialize the auto-dream subsystem.
    Call once at startup (or per-test in setUp for a fresh closure).
    """
    last_session_scan_at: list[float] = [0.0]  # mutable via list cell

    async def run_auto_dream(context: Any, append_system_message: Optional[Callable] = None) -> None:
        cfg = _get_config()

        if not _is_gate_open():
            return

        # --- Time gate ---
        try:
            last_at = await read_last_consolidated_at()
        except Exception as exc:
            logger.debug("[autoDream] readLastConsolidatedAt failed: %s", exc)
            return

        hours_since = (time.time() * 1000 - last_at) / 3_600_000
        if hours_since < cfg.min_hours:
            return

        # --- Scan throttle ---
        since_scan_ms = time.time() * 1000 - last_session_scan_at[0]
        if since_scan_ms < SESSION_SCAN_INTERVAL_MS:
            logger.debug(
                "[autoDream] scan throttle — last scan was %ds ago",
                int(since_scan_ms / 1000),
            )
            return
        last_session_scan_at[0] = time.time() * 1000

        # --- Session gate ---
        try:
            session_ids = await list_sessions_touched_since(last_at)
        except Exception as exc:
            logger.debug("[autoDream] listSessionsTouchedSince failed: %s", exc)
            return

        # Exclude the current session
        current_session = _get_session_id()
        if current_session:
            session_ids = [sid for sid in session_ids if sid != current_session]

        if len(session_ids) < cfg.min_sessions:
            logger.debug(
                "[autoDream] skip — %d sessions since last consolidation, need %d",
                len(session_ids),
                cfg.min_sessions,
            )
            return

        # --- Lock ---
        try:
            prior_mtime = await try_acquire_consolidation_lock()
        except Exception as exc:
            logger.debug("[autoDream] lock acquire failed: %s", exc)
            return

        if prior_mtime is None:
            return

        logger.debug(
            "[autoDream] firing — %.1fh since last, %d sessions to review",
            hours_since,
            len(session_ids),
        )

        memory_root = _get_auto_mem_path()
        transcript_dir = _get_transcript_dir()

        extra = (
            f"\n\n**Tool constraints for this run:** Bash is restricted to read-only commands. "
            f"\n\nSessions since last consolidation ({len(session_ids)}):\n"
            + "\n".join(f"- {sid}" for sid in session_ids)
        )
        prompt = build_consolidation_prompt(memory_root, transcript_dir, extra)

        try:
            # In real impl: call runForkedAgent with the prompt
            # Here: log and no-op
            logger.debug("[autoDream] would run forked agent with prompt (%d chars)", len(prompt))

            logger.debug("[autoDream] completed")

        except Exception as exc:
            logger.debug("[autoDream] fork failed: %s", exc)
            await rollback_consolidation_lock(prior_mtime)

    global _runner
    _runner = run_auto_dream


async def execute_auto_dream(
    context: Any,
    append_system_message: Optional[Callable] = None,
) -> None:
    """
    Entry point from stop hooks. No-op until init_auto_dream() has been called.
    Per-turn cost when enabled: one config read + one stat.
    """
    if _runner is not None:
        await _runner(context, append_system_message)

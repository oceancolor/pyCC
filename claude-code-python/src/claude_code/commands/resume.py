# 原始 TS: commands/resume/index.ts + resume.tsx
"""Resume command - restore a previous conversation session."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


async def list_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """Return recent sessions eligible for resumption.

    TODO: Read from ~/.claude/sessions/ or the session store.
    """
    return []


async def load_session(session_id: str) -> dict[str, Any] | None:
    """Load a session by ID (or fuzzy search by title/content).

    TODO: Deserialize from disk.
    """
    logger.debug("load_session: %s (stub)", session_id)
    return None


async def run(args: str = "", context: Any = None) -> dict[str, Any]:
    """Entry point called by the command dispatcher.

    *args* may be a session ID, a search term, or empty (show picker).
    """
    session_id = args.strip()

    if not session_id:
        sessions = await list_sessions()
        if not sessions:
            return {"type": "text", "value": "No previous sessions found."}
        # TODO: Return an interactive picker component
        lines = ["Previous sessions:"]
        for s in sessions:
            lines.append(f"  {s.get('id', '?')} — {s.get('title', '(untitled)')}")
        return {"type": "text", "value": "\n".join(lines)}

    session = await load_session(session_id)
    if session is None:
        return {"type": "text", "value": f"Session '{session_id}' not found."}

    # TODO: Restore message history into current context
    return {"type": "resume", "session": session}

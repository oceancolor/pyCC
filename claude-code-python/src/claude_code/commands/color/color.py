"""
Ported from: commands/color/color.ts

/color command — set or reset the agent's display color for swarm sessions.
Available colors and the reset aliases are provided; validates input before
saving to the session transcript.
"""
from __future__ import annotations

from typing import Callable, Optional

# ---------------------------------------------------------------------------
# Available colors (mirrors AGENT_COLORS in agentColorManager.ts)
# ---------------------------------------------------------------------------

AGENT_COLORS = [
    "red", "orange", "yellow", "green", "blue", "purple", "pink", "cyan",
]

RESET_ALIASES = {"default", "reset", "none", "gray", "grey"}


# ---------------------------------------------------------------------------
# Stub helpers — real implementations live in utils/session_storage and
# utils/teammate.
# ---------------------------------------------------------------------------

def _is_teammate() -> bool:
    """Return True when running as a swarm teammate (name/color are assigned by leader)."""
    try:
        from claude_code.utils.teammate import is_teammate  # type: ignore[import]
        return is_teammate()
    except ImportError:
        return False


def _get_session_id() -> str:
    try:
        from claude_code.bootstrap.state import get_session_id  # type: ignore[import]
        return get_session_id()
    except ImportError:
        import uuid
        return str(uuid.uuid4())


def _get_transcript_path() -> str:
    try:
        from claude_code.utils.session_storage import get_transcript_path  # type: ignore[import]
        return get_transcript_path()
    except ImportError:
        import os
        return os.path.join(os.path.expanduser("~"), ".claude", "transcript.jsonl")


async def _save_agent_color(session_id: str, color: str, transcript_path: str) -> None:
    try:
        from claude_code.utils.session_storage import save_agent_color  # type: ignore[import]
        await save_agent_color(session_id, color, transcript_path)
    except ImportError:
        pass  # Non-fatal for the Python port


# ---------------------------------------------------------------------------
# Command entry point
# ---------------------------------------------------------------------------

async def call(
    on_done: Callable[[str, dict], None],
    context: object,
    args: str,
) -> None:
    """
    Handle /color [color|reset] command.

    Parameters
    ----------
    on_done:
        Callback that accepts (message: str, options: dict).  Mirrors
        LocalJSXCommandOnDone from the TS source.
    context:
        ToolUseContext + LocalJSXCommandContext (duck-typed).
    args:
        Raw argument string from the REPL.
    """
    # Teammates cannot choose their own color
    if _is_teammate():
        on_done(
            "Cannot set color: This session is a swarm teammate. "
            "Teammate colors are assigned by the team leader.",
            {"display": "system"},
        )
        return

    if not args or not args.strip():
        color_list = ", ".join(AGENT_COLORS)
        on_done(
            f"Please provide a color. Available colors: {color_list}, default",
            {"display": "system"},
        )
        return

    color_arg = args.strip().lower()

    # Handle reset to default
    if color_arg in RESET_ALIASES:
        session_id = _get_session_id()
        transcript_path = _get_transcript_path()
        await _save_agent_color(session_id, "default", transcript_path)

        # Update app state if possible
        try:
            set_app_state: Optional[Callable] = getattr(context, "set_app_state", None)
            if set_app_state is not None:
                def _reset_color(prev: dict) -> dict:
                    updated = dict(prev)
                    sac = dict(prev.get("standalone_agent_context") or {})
                    sac["color"] = None
                    updated["standalone_agent_context"] = sac
                    return updated
                set_app_state(_reset_color)
        except Exception:
            pass

        on_done("Session color reset to default", {"display": "system"})
        return

    if color_arg not in AGENT_COLORS:
        color_list = ", ".join(AGENT_COLORS)
        on_done(
            f'Invalid color "{color_arg}". Available colors: {color_list}, default',
            {"display": "system"},
        )
        return

    session_id = _get_session_id()
    transcript_path = _get_transcript_path()
    await _save_agent_color(session_id, color_arg, transcript_path)

    # Reflect immediately in app state
    try:
        set_app_state = getattr(context, "set_app_state", None)
        if set_app_state is not None:
            def _apply_color(prev: dict) -> dict:
                updated = dict(prev)
                sac = dict(prev.get("standalone_agent_context") or {})
                sac["color"] = color_arg
                updated["standalone_agent_context"] = sac
                return updated
            set_app_state(_apply_color)
    except Exception:
        pass

    on_done(f"Session color set to: {color_arg}", {"display": "system"})

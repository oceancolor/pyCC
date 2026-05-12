"""
Get next permission mode - determines the next permission mode when cycling.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def get_next_permission_mode(
    tool_permission_context: Any,
    team_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Determines the next permission mode when cycling through modes with Shift+Tab."""
    mode = getattr(tool_permission_context, "mode", "default")
    is_bypass_available = getattr(tool_permission_context, "isBypassPermissionsModeAvailable", False)

    if mode == "default":
        return "acceptEdits"
    elif mode == "acceptEdits":
        return "plan"
    elif mode == "plan":
        if is_bypass_available:
            return "bypassPermissions"
        return "default"
    elif mode == "bypassPermissions":
        return "default"
    elif mode == "dontAsk":
        return "default"
    else:
        return "default"


def cycle_permission_mode(
    tool_permission_context: Any,
    team_context: Optional[Dict[str, Any]] = None,
) -> Tuple[str, Any]:
    """Computes the next permission mode and prepares the context for it."""
    next_mode = get_next_permission_mode(tool_permission_context, team_context)
    # Return (next_mode, context) — context may need cleanup for certain mode transitions
    new_ctx = _transition_permission_mode(
        getattr(tool_permission_context, "mode", "default"),
        next_mode,
        tool_permission_context,
    )
    return next_mode, new_ctx


def _transition_permission_mode(
    current_mode: str,
    next_mode: str,
    ctx: Any,
) -> Any:
    """Apply any necessary context changes when transitioning modes."""
    # In auto mode (ANT-only), dangerous permissions would be stripped here.
    # For the Python port, we just return the context unchanged.
    return ctx

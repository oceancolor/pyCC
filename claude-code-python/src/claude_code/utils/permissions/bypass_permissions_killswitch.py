"""
Bypass permissions killswitch - checks and disables bypass permissions mode if needed.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

_bypass_permissions_check_ran: bool = False
_auto_mode_check_ran: bool = False


async def check_and_disable_bypass_permissions_if_needed(
    tool_permission_context: Any,
    set_app_state: Callable,
) -> None:
    """Check if bypassPermissions should be disabled based on gate. Run once."""
    global _bypass_permissions_check_ran
    if _bypass_permissions_check_ran:
        return
    _bypass_permissions_check_ran = True

    if not getattr(tool_permission_context, "is_bypass_permissions_mode_available", False):
        return

    try:
        from .permission_mode import PermissionMode
        should_disable = await _should_disable_bypass_permissions()
        if not should_disable:
            return

        def updater(prev: Any) -> Any:
            new_ctx = _create_disabled_bypass_context(prev.toolPermissionContext)
            return {**prev.__dict__, "toolPermissionContext": new_ctx}

        set_app_state(updater)
    except Exception:
        pass


def reset_bypass_permissions_check() -> None:
    """Reset the run-once flag for the bypass check."""
    global _bypass_permissions_check_ran
    _bypass_permissions_check_ran = False


async def check_and_disable_auto_mode_if_needed(
    tool_permission_context: Any,
    set_app_state: Callable,
    fast_mode: bool = False,
) -> None:
    """Check if auto mode should be disabled."""
    global _auto_mode_check_ran
    if _auto_mode_check_ran:
        return
    _auto_mode_check_ran = True
    # Auto mode is ANT-only; stub does nothing.


def reset_auto_mode_gate_check() -> None:
    """Reset the run-once flag for the auto mode check."""
    global _auto_mode_check_ran
    _auto_mode_check_ran = False


async def _should_disable_bypass_permissions() -> bool:
    """Check if bypass permissions should be disabled (stub)."""
    return False


def _create_disabled_bypass_context(ctx: Any) -> Any:
    """Create a new tool permission context with bypass permissions disabled."""
    if hasattr(ctx, "__dict__"):
        new_ctx = type(ctx).__new__(type(ctx))
        new_ctx.__dict__.update(ctx.__dict__)
        new_ctx.isBypassPermissionsModeAvailable = False
        return new_ctx
    return ctx

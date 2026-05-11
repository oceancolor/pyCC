"""
Leader Permission Bridge.

Module-level bridge that allows the REPL to register its set_tool_use_confirm_queue
and set_tool_permission_context functions for in-process teammates to use.

When an in-process teammate requests permissions, it uses the standard
ToolUseConfirm dialog rather than the worker permission badge. This bridge
makes the REPL's queue setter and permission context setter accessible
from non-UI code in the in-process runner.

原始 TS: utils/swarm/leaderPermissionBridge.ts
"""

from typing import Callable, Optional, Any

# Type aliases for the registered functions
SetToolUseConfirmQueueFn = Callable[[Callable[[list], list]], None]
SetToolPermissionContextFn = Callable[..., None]

_registered_setter: Optional[SetToolUseConfirmQueueFn] = None
_registered_permission_context_setter: Optional[SetToolPermissionContextFn] = None


def register_leader_tool_use_confirm_queue(setter: SetToolUseConfirmQueueFn) -> None:
    """Register the REPL's setToolUseConfirmQueue function."""
    global _registered_setter
    _registered_setter = setter


def get_leader_tool_use_confirm_queue() -> Optional[SetToolUseConfirmQueueFn]:
    """Get the registered tool use confirm queue setter, or None if not registered."""
    return _registered_setter


def unregister_leader_tool_use_confirm_queue() -> None:
    """Unregister the tool use confirm queue setter."""
    global _registered_setter
    _registered_setter = None


def register_leader_set_tool_permission_context(setter: SetToolPermissionContextFn) -> None:
    """Register the REPL's setToolPermissionContext function."""
    global _registered_permission_context_setter
    _registered_permission_context_setter = setter


def get_leader_set_tool_permission_context() -> Optional[SetToolPermissionContextFn]:
    """Get the registered tool permission context setter, or None if not registered."""
    return _registered_permission_context_setter


def unregister_leader_set_tool_permission_context() -> None:
    """Unregister the tool permission context setter."""
    global _registered_permission_context_setter
    _registered_permission_context_setter = None

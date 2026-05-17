"""
Hooks package.
Ported from: src/hooks/ (TypeScript)

Provides the session-level hook system for Claude Code:
  - HookEvent  — enum of lifecycle hook points
  - HookResult / HookDecision — per-hook and aggregated results
  - HookRegistry  — session-scoped registry for registering and firing hooks
  - HookType     — alias kept for backwards compatibility
"""
from __future__ import annotations

from .types import (
    HookEvent,
    HookResult,
    HookDecision,
    AggregatedHookResult,
    HookInput,
    CommandHook,
    FunctionHook,
    FunctionHookCallback,
    HookCommand,
    HookJSONOutput,
    SyncHookJSONOutput,
    AsyncHookJSONOutput,
    SessionHookEntry,
    SessionHookMatcher,
    SessionHooksState,
    REPLHookContext,
    PostSamplingHook,
    HookResultMessage,
    HOOK_EVENTS,
    is_hook_event,
)
from .registry import HookRegistry

# Alias kept for backwards compatibility — TypeScript had a `HookType` export.
HookType = HookEvent

__all__ = [
    "HookEvent",
    "HookResult",
    "HookDecision",
    "HookType",
    "AggregatedHookResult",
    "HookInput",
    "CommandHook",
    "FunctionHook",
    "FunctionHookCallback",
    "HookCommand",
    "HookJSONOutput",
    "SyncHookJSONOutput",
    "AsyncHookJSONOutput",
    "SessionHookEntry",
    "SessionHookMatcher",
    "SessionHooksState",
    "REPLHookContext",
    "PostSamplingHook",
    "HookResultMessage",
    "HOOK_EVENTS",
    "is_hook_event",
    "HookRegistry",
]

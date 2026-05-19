"""Shared tool utilities.

Contains cross-cutting helpers used by multiple tool implementations.

Ported from: tools/shared/ (TypeScript)

Exported symbols
----------------
GitOperationResult
    Named result type for git operations performed inside tool calls.
SpawnTeammateConfig
    Configuration for spawning a parallel teammate agent.
spawn_multi_agent
    Helper that spawns one or more teammate agents in parallel.
make_tool_result
    Factory for building a well-formed tool-result dict.
truncate_tool_result
    Truncate oversized tool output to avoid hitting context limits.
"""
from __future__ import annotations

from claude_code.tools.shared.git_operation_tracking import GitOperationResult
from claude_code.tools.shared.spawn_multi_agent import SpawnTeammateConfig, spawn_multi_agent
from claude_code.tools.shared.tool_helpers import make_tool_result, truncate_tool_result

__all__ = [
    "GitOperationResult",
    "SpawnTeammateConfig",
    "spawn_multi_agent",
    "make_tool_result",
    "truncate_tool_result",
]

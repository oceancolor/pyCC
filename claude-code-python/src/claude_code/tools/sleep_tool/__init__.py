"""SleepTool package.

Re-exports the SleepTool class from its implementation module.

SleepTool pauses agent execution for a specified number of milliseconds.
It is primarily used in automated tests and in scenarios where the agent
needs to wait for an external process (e.g. a build, a server restart, or
a file-system event) to settle before proceeding.

Excessive use of SleepTool is a code smell — prefer polling with a shorter
sleep interval over a single large sleep.

Ported from: tools/SleepTool/ (TypeScript)

Usage::

    from claude_code.tools.sleep_tool import SleepTool
"""
from __future__ import annotations

from claude_code.tools.sleep_tool.sleep_tool import SleepTool

__all__ = ["SleepTool"]

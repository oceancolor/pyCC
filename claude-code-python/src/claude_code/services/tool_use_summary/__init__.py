"""Tool-use summary service.

Generates a concise human-readable summary of the tool calls made during
an agent turn.  The summary is shown in the UI after the turn completes
and is also recorded in telemetry.

Ported from: src/services/toolUseSummary/ (TypeScript)

Usage::

    from claude_code.services.tool_use_summary import (
        generate_tool_use_summary,
        ToolInfo,
    )
"""
from __future__ import annotations

from claude_code.services.tool_use_summary.tool_use_summary_generator import (
    generate_tool_use_summary,
    ToolInfo,
)

__all__ = [
    "generate_tool_use_summary",
    "ToolInfo",
]

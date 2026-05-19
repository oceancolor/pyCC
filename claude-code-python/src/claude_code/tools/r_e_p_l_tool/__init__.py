"""REPLTool package.

Re-exports the REPL primitive tool factories and related constants.

The REPL tool set provides a stateful, persistent shell session where
variables and state survive between individual command calls.  This is
the preferred execution environment for iterative data analysis and
exploration.

Ported from: tools/REPLTool/ (TypeScript)

Usage::

    from claude_code.tools.r_e_p_l_tool import (
        get_repl_primitive_tools,
        get_repl_primitive_tool_names,
        REPL_TOOL_NAME,
        REPL_ONLY_TOOLS,
        is_repl_mode_enabled,
    )
"""
from __future__ import annotations

from claude_code.tools.r_e_p_l_tool.repl_tool import (
    get_repl_primitive_tools,
    get_repl_primitive_tool_names,
)
from claude_code.tools.r_e_p_l_tool.repl_constants import (
    REPL_TOOL_NAME,
    REPL_ONLY_TOOLS,
    is_repl_mode_enabled,
)

__all__ = [
    "get_repl_primitive_tools",
    "get_repl_primitive_tool_names",
    "REPL_TOOL_NAME",
    "REPL_ONLY_TOOLS",
    "is_repl_mode_enabled",
]

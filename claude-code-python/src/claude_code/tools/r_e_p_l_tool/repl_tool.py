"""REPL tool stub. Ported from REPLTool."""
from __future__ import annotations
from typing import Any
from claude_code.tools.r_e_p_l_tool.repl_constants import REPL_TOOL_NAME, is_repl_mode_enabled

DESCRIPTION = "Execute a batch of tool calls in a sandboxed REPL environment"


class REPLTool:
    name = REPL_TOOL_NAME
    description = DESCRIPTION

    def is_enabled(self) -> bool:
        return is_repl_mode_enabled()

    async def call(self, code: str = "", **kwargs: Any) -> dict:
        return {"error": "REPL tool not fully implemented"}

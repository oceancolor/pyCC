"""
SyntheticOutputTool — structured output for non-interactive sessions.
Ported from SyntheticOutputTool/SyntheticOutputTool.ts.
"""
from __future__ import annotations
from typing import Any

SYNTHETIC_OUTPUT_TOOL_NAME = "StructuredOutput"


def is_synthetic_output_tool_enabled(is_non_interactive: bool = False) -> bool:
    return is_non_interactive


class SyntheticOutputTool:
    name = SYNTHETIC_OUTPUT_TOOL_NAME
    description = "Structured output tool for non-interactive sessions."
    is_read_only = True

    async def call(self, output: Any = None, context: Any = None) -> dict:
        import json
        if isinstance(output, str):
            return {"type": "success", "output": output}
        return {"type": "success", "output": json.dumps(output) if output else ""}

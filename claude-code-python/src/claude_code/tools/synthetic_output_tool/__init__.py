"""SyntheticOutputTool package.

Re-exports the SyntheticOutputTool class from its implementation module.

SyntheticOutputTool injects a synthetic (fake) tool-result message into the
conversation.  This is used internally to:

- Replay cached results from a previous session without re-running tools.
- Construct test fixtures that simulate tool outputs.
- Fill in tool-result slots when a tool call was aborted or skipped due
  to permission denial.

Ported from: tools/SyntheticOutputTool/ (TypeScript)

Usage::

    from claude_code.tools.synthetic_output_tool import SyntheticOutputTool
"""
from __future__ import annotations

from claude_code.tools.synthetic_output_tool.synthetic_output_tool import SyntheticOutputTool

__all__ = ["SyntheticOutputTool"]

"""GrepTool package.

Re-exports the GrepTool class from its implementation module.

GrepTool searches file contents for a pattern (regular expression or
literal string) and returns matching lines with their file paths and
line numbers.  It is faster than running ``grep`` via BashTool for
large codebases because it operates natively without spawning a shell.

Ported from: tools/GrepTool/ (TypeScript)

Usage::

    from claude_code.tools.grep_tool import GrepTool
"""
from __future__ import annotations

from claude_code.tools.grep_tool.grep_tool import GrepTool

__all__ = ["GrepTool"]

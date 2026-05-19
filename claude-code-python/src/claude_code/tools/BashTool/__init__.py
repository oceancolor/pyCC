"""BashTool alias package.

Re-exports the BashTool class from the canonical ``bash_tool`` sub-package.
The capital-cased ``BashTool/`` directory mirrors the original TypeScript
source layout where ``tools/BashTool/`` was the entry point.

The BashTool executes arbitrary shell commands and streams their output
back to the model.  It is the most powerful and most frequently used tool
in Claude Code.

Ported from: tools/BashTool/ (TypeScript)

Usage::

    from claude_code.tools.BashTool import BashTool

Notes
-----
Prefer importing from ``claude_code.tools.bash_tool`` in new code.
This package exists for backward compatibility with the TS directory layout.
"""
from __future__ import annotations

from claude_code.tools.bash_tool import BashTool

__all__ = ["BashTool"]

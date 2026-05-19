"""GlobTool package.

Re-exports the GlobTool class from its implementation module.

GlobTool performs fast file pattern matching across the workspace using
standard glob syntax (e.g. ``**/*.ts``, ``src/**/*.py``).  Results are
sorted by modification time so recently-changed files appear first.

For content-based search (searching inside files), use ``GrepTool``
instead.  For open-ended searches that may require multiple rounds of
globbing and grepping, prefer spawning an Agent sub-task.

Ported from: tools/GlobTool/ (TypeScript)

Usage::

    from claude_code.tools.glob_tool import GlobTool
"""
from __future__ import annotations

from claude_code.tools.glob_tool.glob_tool import GlobTool

__all__ = ["GlobTool"]

"""NotebookEditTool package.

Re-exports the NotebookEditTool class from its implementation module.

NotebookEditTool edits Jupyter notebook (``.ipynb``) files by targeting
individual cells.  It supports updating cell source, inserting new cells,
and deleting cells without touching the rest of the notebook structure
(metadata, outputs, etc.).

This is preferred over using ``FileEditTool`` on ``.ipynb`` files because
the raw JSON structure of notebooks is fragile and the cell-based API
ensures the notebook remains valid.

Ported from: tools/NotebookEditTool/ (TypeScript)

Usage::

    from claude_code.tools.notebook_edit_tool import NotebookEditTool
"""
from __future__ import annotations

from claude_code.tools.notebook_edit_tool.notebook_edit_tool import NotebookEditTool

__all__ = ["NotebookEditTool"]

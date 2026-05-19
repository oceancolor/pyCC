"""FileReadTool package.

Re-exports the FileReadTool class from its implementation module.

FileReadTool reads the contents of a local file, optionally with a line
offset and limit.  Results are formatted with ``cat -n`` style line numbers
(1-indexed) to help the agent reference specific lines when making edits.

The tool also supports reading images (PNG, JPEG, etc.) and Jupyter
notebooks (``.ipynb``), returning their content in a model-friendly format.

Ported from: tools/FileReadTool/ (TypeScript)

Usage::

    from claude_code.tools.file_read_tool import FileReadTool
"""
from __future__ import annotations

from claude_code.tools.file_read_tool.file_read_tool import FileReadTool

__all__ = ["FileReadTool"]
